-- | Verificación estática: alcance y tipos, en ese orden (etapas @scope@ y
-- @typecheck@ del contrato). Todo error es un valor 'CheckError'; ninguna
-- función de este módulo lanza excepciones.
module Engine.TypeCheck
  ( CheckError (..)
  , Stage (..)
  , freeVars
  , scopeCheck
  , typeOf
  , checkProgram
  , errorStage
  , errorCode
  , errorMessage
  ) where

import Control.Monad (unless)

import Engine.Env (Env, extend, lookupVar, names)
import Engine.Types

-- | Etapa del contrato en la que se bloquea un programa.
data Stage = Scope | TypeCheck
  deriving (Show, Eq)

-- FP[Tipos algebraicos]
-- | Fallos de scope/typecheck tipados; 'errorCode' los traduce al contrato CLI.
data CheckError
  = UnboundVariable Name
  | OperandMismatch BinOp Type Type
  | UnaryMismatch UnOp Type
  | InMismatch Type Type -- ^ tipo de @value@, tipo de la opción
  | ConditionNotBool Type
  | BranchMismatch Type Type
  | NotAFunction Type
  | ArgumentMismatch Type Type -- ^ esperado, recibido
  | NonBaseResult Type
  deriving (Show, Eq)

-- FP[Recursión] FP[Igualaciones] FP[Listas por comprensión] FP[map/filter/fold] FP[Funciones de listas]
-- | Variables libres en orden de aparición (izquierda a derecha).
freeVars :: Expr -> [Name]
freeVars (Literal _) = []
freeVars (Var x) = [x]
freeVars (UnaryOp _ e) = freeVars e
freeVars (BinaryOp _ l r) = freeVars l ++ freeVars r
freeVars (In v opts) = concatMap freeVars (v : opts)
freeVars (IfThenElse c t e) = concatMap freeVars [c, t, e]
freeVars (Lam x _ body) = [v | v <- freeVars body, v /= x]
freeVars (App f a) = freeVars f ++ freeVars a

-- FP[Evaluación perezosa] FP[Polimorfismo] FP[Patrones de listas] FP[Funciones totales]
-- | Falla con la primera variable libre que no está en Γ. Por evaluación
-- perezosa, la lista solo se calcula hasta encontrar esa primera variable.
scopeCheck :: Env a -> Expr -> Either CheckError ()
scopeCheck gamma e =
  case [v | v <- freeVars e, v `notElem` names gamma] of
    [] -> Right ()
    (v : _) -> Left (UnboundVariable v)

-- FP[Tipos] FP[Igualaciones] FP[Recursión] FP[Funciones puras] FP[Funciones lambda] FP[Inmutabilidad] FP[Condicionales] FP[Currificación]
-- | Γ ⊢ e : τ. Sintetiza el tipo; los parámetros de 'Lam' vienen anotados,
-- así que no hace falta unificación.
typeOf :: Env Type -> Expr -> Either CheckError Type
typeOf _ (Literal v) = Right (literalType v)
typeOf gamma (Var x) = maybe (Left (UnboundVariable x)) Right (lookupVar x gamma)
typeOf gamma (UnaryOp Not e) = do
  t <- typeOf gamma e
  unless (t == TBool) (Left (UnaryMismatch Not t))
  Right TBool
typeOf gamma (BinaryOp op l r) = do
  tl <- typeOf gamma l
  tr <- typeOf gamma r
  maybe (Left (OperandMismatch op tl tr)) Right (binOpType op tl tr)
typeOf gamma (In v opts) = do
  tv <- typeOf gamma v
  mapM_ (option tv) opts
  Right TBool
  where
    option tv o = do
      to <- typeOf gamma o
      unless (comparable tv to) (Left (InMismatch tv to))
typeOf gamma (IfThenElse c t e) = do
  tc <- typeOf gamma c
  unless (tc == TBool) (Left (ConditionNotBool tc))
  tt <- typeOf gamma t
  te <- typeOf gamma e
  unless (tt == te) (Left (BranchMismatch tt te))
  Right tt
typeOf gamma (Lam x t body) = TArrow t <$> typeOf (extend x t gamma) body
typeOf gamma (App f a) = do
  tf <- typeOf gamma f
  ta <- typeOf gamma a
  case tf of
    TArrow param result
      | param == ta -> Right result
      | otherwise -> Left (ArgumentMismatch param ta)
    _ -> Left (NotAFunction tf)

-- FP[Condicionales]
-- | Tipo del resultado de un operador binario, o 'Nothing' si los operandos no
-- sirven. Int se promueve a Decimal solo acá, dentro de operadores
-- (@contracts/README.md@ §1); en 'App' no hay promoción.
binOpType :: BinOp -> Type -> Type -> Maybe Type
binOpType op a b
  | op `elem` [Add, Sub, Mul], numeric = Just (if a == TInt && b == TInt then TInt else TDecimal)
  | op == Div, numeric = Just TDecimal
  | op == Mod, a == TInt, b == TInt = Just TInt
  | op `elem` [Gt, Lt, Gte, Lte], numeric = Just TBool
  | op `elem` [Eq, Neq], comparable a b = Just TBool
  | op `elem` [And, Or], a == TBool, b == TBool = Just TBool
  | otherwise = Nothing
  where
    numeric = isNumeric a && isNumeric b

-- | Se pueden comparar por igualdad: el mismo tipo base, o dos numéricos.
comparable :: Type -> Type -> Bool
comparable a b = (a == b && isBase a) || (isNumeric a && isNumeric b)

-- FP[Funciones puras]
-- | Alcance, luego tipos, luego exige que el resultado sea un tipo base.
checkProgram :: Env Type -> Program -> Either CheckError Type
checkProgram gamma (Program e) = do
  scopeCheck gamma e
  t <- typeOf gamma e
  unless (isBase t) (Left (NonBaseResult t))
  Right t

-- | Clasifica el error para seleccionar la etapa y exit code externos.
errorStage :: CheckError -> Stage
errorStage (UnboundVariable _) = Scope
errorStage _ = TypeCheck

-- | Código estable del contrato (@contracts/README.md@).
errorCode :: CheckError -> String
errorCode (UnboundVariable _) = "UNBOUND_VARIABLE"
errorCode (OperandMismatch {}) = "OPERAND_MISMATCH"
errorCode (UnaryMismatch _ _) = "OPERAND_MISMATCH"
errorCode (InMismatch _ _) = "OPERAND_MISMATCH"
errorCode (ConditionNotBool _) = "CONDITION_NOT_BOOL"
errorCode (BranchMismatch _ _) = "BRANCH_MISMATCH"
errorCode (NotAFunction _) = "NOT_A_FUNCTION"
errorCode (ArgumentMismatch _ _) = "ARGUMENT_MISMATCH"
errorCode (NonBaseResult _) = "NON_BASE_RESULT"

-- | Mensaje legible; el código estable se obtiene con 'errorCode'.
errorMessage :: CheckError -> String
errorMessage (UnboundVariable x) = "variable no declarada: " ++ x
errorMessage (OperandMismatch op a b) =
  opSymbol op ++ " no admite " ++ renderType a ++ " y " ++ renderType b
errorMessage (UnaryMismatch op t) = unOpSymbol op ++ " no admite " ++ renderType t
errorMessage (InMismatch v o) =
  "IN compara un valor " ++ renderType v ++ " con una opción " ++ renderType o
errorMessage (ConditionNotBool t) = "la condición es " ++ renderType t ++ ", se esperaba Bool"
errorMessage (BranchMismatch a b) = "then: " ++ renderType a ++ ", else: " ++ renderType b
errorMessage (NotAFunction t) = "se aplica un valor de tipo " ++ renderType t ++ ", que no es función"
errorMessage (ArgumentMismatch expected got) =
  "argumento " ++ renderType got ++ ", se esperaba " ++ renderType expected
errorMessage (NonBaseResult t) = "el resultado es " ++ renderType t ++ ", se esperaba Int, Decimal, Bool o String"
