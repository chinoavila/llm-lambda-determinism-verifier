-- | Evaluador big-step (etapa @execution@ del contrato). Solo se llama sobre
-- programas que ya pasaron 'Engine.TypeCheck.checkProgram'; por eso un
-- 'EvalError' nunca debería ocurrir: si ocurre, es un bug del motor (exit 70).
module Engine.Eval
  ( Value (..)
  , EvalError (..)
  , eval
  , evalProgram
  , evalErrorMessage
  ) where

import Engine.Env (Env, extend, lookupVar)
import Engine.Types

-- FP[Tipos algebraicos] FP[Funciones lambda]
-- | v ::= literal | ⟨λx. e, ρ⟩. Una clausura guarda el entorno donde se
-- definió la lambda (alcance léxico).
data Value
  = VBase LiteralValue
  | VClosure Name Expr (Env Value)
  deriving (Show, Eq)

-- | Estados atascados: imposibles en un programa bien tipado.
data EvalError
  = StuckVar Name
  | StuckOp BinOp
  | StuckIf
  | StuckApp
  | StuckResult
  deriving (Show, Eq)

-- FP[Recursión] FP[Igualaciones] FP[Funciones puras] FP[Inmutabilidad] FP[Condicionales]
-- | ρ ⊢ e ⇓ v, con llamada por valor: en 'App' se evalúa el argumento antes
-- de entrar al cuerpo. En 'IfThenElse' solo se evalúa la rama elegida.
eval :: Env Value -> Expr -> Either EvalError Value
eval _ (Literal v) = Right (VBase v)
eval env (Var x) = maybe (Left (StuckVar x)) Right (lookupVar x env)
eval env (BinaryOp op l r) = do
  a <- eval env l
  b <- eval env r
  case (a, b) of
    (VBase x, VBase y) -> VBase . VBool <$> applyOp op x y
    _ -> Left (StuckOp op)
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

-- FP[Patrones constantes]
-- | Mismo reparto que 'Engine.TypeCheck.operandsOk': comparaciones sobre
-- Int, @==@ sobre un mismo tipo base, lógicos sobre Bool.
applyOp :: BinOp -> LiteralValue -> LiteralValue -> Either EvalError Bool
applyOp Gt (VInt a) (VInt b) = Right (a > b)
applyOp Lt (VInt a) (VInt b) = Right (a < b)
applyOp Gte (VInt a) (VInt b) = Right (a >= b)
applyOp Lte (VInt a) (VInt b) = Right (a <= b)
applyOp Eq a b
  | literalType a == literalType b = Right (a == b)
applyOp And (VBool a) (VBool b) = Right (a && b)
applyOp Or (VBool a) (VBool b) = Right (a || b)
applyOp op _ _ = Left (StuckOp op)

-- FP[Composición] FP[Polimorfismo]
-- | Evalúa el programa con los datos del caso. El resultado debe ser un
-- valor base (lo garantiza @NON_BASE_RESULT@ en el typechecker).
evalProgram :: Env LiteralValue -> Program -> Either EvalError LiteralValue
evalProgram env (Program e) = do
  v <- eval (map (fmap VBase) env) e
  case v of
    VBase lit -> Right lit
    VClosure {} -> Left StuckResult

evalErrorMessage :: EvalError -> String
evalErrorMessage (StuckVar x) = "variable sin valor en tiempo de ejecución: " ++ x
evalErrorMessage (StuckOp op) = "operandos inválidos para " ++ opSymbol op
evalErrorMessage StuckIf = "la condición no es un booleano"
evalErrorMessage StuckApp = "se aplicó un valor que no es función"
evalErrorMessage StuckResult = "el resultado es una función"
