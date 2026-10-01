-- | Evaluador big-step (etapa @execution@ del contrato). Solo se llama sobre
-- programas que ya pasaron 'Engine.TypeCheck.checkProgram'.
--
-- Hay dos clases de fallas, y son valores, no excepciones:
--
-- * 'Runtime': errores del programa que el sistema de tipos no puede
--   descartar (dividir por cero, desbordar). Son desenlaces legítimos:
--   @runtime_error@, exit 4.
-- * Estados atascados ('StuckVar', 'StuckOp', ...): imposibles en un programa
--   bien tipado. Si ocurren, es un bug del motor (exit 70).
module Engine.Eval
  ( Value (..)
  , RuntimeError (..)
  , EvalError (..)
  , eval
  , evalProgram
  , evalErrorMessage
  , runtimeErrorCode
  , runtimeErrorMessage
  ) where

import Engine.Env (Env, extend, lookupVar)
import Engine.Number (decimalInRange, intInRange)
import Engine.Types


-- Qué hace este módulo (etapa 4 del motor, "execution"):
-- recibe el Program que ya pasó TypeCheck.hs y los valores del caso
-- (Env LiteralValue) y calcula el resultado de la regla.
--   eval: recorre la expresión y calcula su valor. Ej.: con credit_score = 750,
--     credit_score > 700 da true.
--   evalProgram: arma el entorno de valores, llama a eval y devuelve el resultado.
--   applyOp: hace la cuenta de cada operador (+, -, *, /, %, >, ==, ...).
-- Las cuentas son exactas: Int y Rational, sin Double (ver Number.hs).
-- Errores posibles (runtime_error): DIVISION_BY_ZERO y NUMERIC_OVERFLOW.
-- Los errores "Stuck..." no deberían ocurrir nunca: si aparecen, es un bug del motor.

-- FP[Tipos algebraicos] FP[Funciones lambda]
-- | v ::= literal | ⟨λx. e, ρ⟩. Una clausura guarda el entorno donde se
-- definió la lambda (alcance léxico).
data Value
  = VBase LiteralValue
  | VClosure Name Expr (Env Value)
  deriving (Show, Eq)

-- | Errores del programa en ejecución (@contracts/README.md@ §1).
-- | Fallo legítimo del programa bien tipado que no puede descartarse estáticamente.
data RuntimeError
  = DivisionByZero
  | NumericOverflow
  deriving (Show, Eq)

-- | Suma de errores runtime y estados atascados imposibles bajo el typechecker.
data EvalError
  = Runtime RuntimeError
  | StuckVar Name
  | StuckOp BinOp
  | StuckUnOp UnOp
  | StuckIn
  | StuckIf
  | StuckApp
  | StuckResult
  deriving (Show, Eq)

-- FP[Recursión] FP[Igualaciones] FP[Funciones puras] FP[Inmutabilidad] FP[Condicionales] FP[Currificación]
-- | ρ ⊢ e ⇓ v, con llamada por valor y de izquierda a derecha. En
-- 'IfThenElse' solo se evalúa la rama elegida; @AND@ y @OR@ cortocircuitan
-- como en Python, así una guarda (@x != 0 AND 10 / x > 2@) protege a la
-- división; 'In' se detiene en la primera opción igual.
eval :: Env Value -> Expr -> Either EvalError Value
eval _ (Literal v) = Right (VBase v)
eval env (Var x) = maybe (Left (StuckVar x)) Right (lookupVar x env)
eval env (UnaryOp Not e) = do
  v <- eval env e
  case v of
    VBase (VBool b) -> Right (VBase (VBool (not b)))
    _ -> Left (StuckUnOp Not)
eval env (BinaryOp op l r)
  | op == And || op == Or = do
      a <- bool =<< eval env l
      -- FP[Evaluación perezosa]
      if a == (op == Or) then Right (VBase (VBool a)) else VBase . VBool <$> (bool =<< eval env r)
  | otherwise = do
      a <- eval env l
      b <- eval env r
      case (a, b) of
        (VBase x, VBase y) -> VBase <$> applyOp op x y
        _ -> Left (StuckOp op)
  where
    bool (VBase (VBool b)) = Right b
    bool _ = Left (StuckOp op)
eval env (In v opts) = do
  a <- base =<< eval env v
  anyEqual a opts
  where
    base (VBase x) = Right x
    base _ = Left StuckIn
    anyEqual _ [] = Right (VBase (VBool False))
    anyEqual a (o : os) = do
      b <- base =<< eval env o
      same <- maybe (Left StuckIn) Right (equal a b)
      if same then Right (VBase (VBool True)) else anyEqual a os
eval env (IfThenElse c t e) = do
  vc <- eval env c
  case vc of
    VBase (VBool True) -> eval env t
    VBase (VBool False) -> eval env e
    _ -> Left StuckIf
eval env (Lam x _ body) = Right (VClosure x body env)
eval env (App f a) = do
  vf <- eval env f
  va <- eval env a
  case vf of
    -- β-reducción: (λx. b) v ⇓ b evaluado en ρ', x ↦ v
    VClosure x body closureEnv -> eval (extend x va closureEnv) body
    _ -> Left StuckApp

-- FP[Patrones constantes] FP[Condicionales]
-- | Mismo reparto que 'Engine.TypeCheck.binOpType'. La aritmética entre dos
-- 'VInt' se hace en 'Integer' y se verifica el rango de 64 bits; con algún
-- 'VDecimal' (o en @/@), en racionales exactos con su propio límite.
applyOp :: BinOp -> LiteralValue -> LiteralValue -> Either EvalError LiteralValue
applyOp op x y = case (x, y) of
  (VInt a, VInt b)
    | op `elem` [Add, Sub, Mul] -> intResult (intArith op (toInteger a) (toInteger b))
    | op == Mod -> if b == 0 then runtime DivisionByZero else intResult (toInteger a `mod` toInteger b)
  _
    | op `elem` [Add, Sub, Mul, Div], Just a <- rational x, Just b <- rational y ->
        if op == Div && b == 0 then runtime DivisionByZero else decimalResult (ratArith op a b)
    | op `elem` [Gt, Lt, Gte, Lte], Just a <- rational x, Just b <- rational y ->
        Right (VBool (compareWith op a b))
    | op == Eq, Just same <- equal x y -> Right (VBool same)
    | op == Neq, Just same <- equal x y -> Right (VBool (not same))
    | otherwise -> Left (StuckOp op)
  where
    intArith Add = (+)
    intArith Sub = (-)
    intArith _ = (*)
    ratArith Add = (+)
    ratArith Sub = (-)
    ratArith Mul = (*)
    ratArith _ = (/)
    compareWith Gt = (>)
    compareWith Lt = (<)
    compareWith Gte = (>=)
    compareWith _ = (<=)
    intResult n = if intInRange n then Right (VInt (fromInteger n)) else runtime NumericOverflow
    decimalResult q = if decimalInRange q then Right (VDecimal q) else runtime NumericOverflow

-- | Eleva un error runtime al tipo común de errores del evaluador.
runtime :: RuntimeError -> Either EvalError a
runtime = Left . Runtime

-- | Convierte un literal numérico a racional; valores no numéricos dan 'Nothing'.
rational :: LiteralValue -> Maybe Rational
rational (VInt n) = Just (toRational n)
rational (VDecimal q) = Just q
rational _ = Nothing

-- | Igualdad de @==@, @!=@ e 'In': exacta entre números (@1 == 1.0@), y entre
-- valores del mismo tipo base. 'Nothing' si no son comparables (atasco).
equal :: LiteralValue -> LiteralValue -> Maybe Bool
equal x y = case (rational x, rational y) of
  (Just a, Just b) -> Just (a == b)
  _
    | literalType x == literalType y -> Just (x == y)
    | otherwise -> Nothing

-- FP[Composición] FP[Polimorfismo]
-- | Evalúa el programa con los datos del caso. El resultado debe ser un
-- valor base (lo garantiza @NON_BASE_RESULT@ en el typechecker).
evalProgram :: Env LiteralValue -> Program -> Either EvalError LiteralValue
evalProgram env (Program e) = do
  v <- eval (map (fmap VBase) env) e
  case v of
    VBase lit -> Right lit
    VClosure {} -> Left StuckResult

-- | Código estable del contrato para un fallo runtime del programa.
runtimeErrorCode :: RuntimeError -> String
runtimeErrorCode DivisionByZero = "DIVISION_BY_ZERO"
runtimeErrorCode NumericOverflow = "NUMERIC_OVERFLOW"

-- | Mensaje humano del error runtime; no se usa como identificador estable.
runtimeErrorMessage :: RuntimeError -> String
runtimeErrorMessage DivisionByZero = "división por cero"
runtimeErrorMessage NumericOverflow =
  "resultado fuera de rango: Int de 64 bits, o Decimal menor a 10^28 con denominador de a lo sumo 10^28"

-- | Convierte cualquier error del evaluador a diagnóstico para stderr.
evalErrorMessage :: EvalError -> String
evalErrorMessage (Runtime err) = runtimeErrorMessage err
evalErrorMessage (StuckVar x) = "variable sin valor en tiempo de ejecución: " ++ x
evalErrorMessage (StuckOp op) = "operandos inválidos para " ++ opSymbol op
evalErrorMessage (StuckUnOp op) = "operando inválido para " ++ unOpSymbol op
evalErrorMessage StuckIn = "IN con valores que no se pueden comparar"
evalErrorMessage StuckIf = "la condición no es un booleano"
evalErrorMessage StuckApp = "se aplicó un valor que no es función"
evalErrorMessage StuckResult = "el resultado es una función"
