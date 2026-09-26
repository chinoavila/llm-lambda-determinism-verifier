-- | Tipos del AST del DSL STLC.
--
-- Gramática acordada en @contracts/ast-schema.json@ (reglas en
-- @contracts/README.md@):
--   Tipos        τ ::= Int | Bool | String | τ → τ
--   Expresiones  e ::= Literal | Var | BinaryOp | IfThenElse | Lam | App
module Engine.Types
  ( Name
  , Type (..)
  , LiteralValue (..)
  , BinOp (..)
  , Expr (..)
  , Program (..)
  , isBase
  , literalType
  , renderType
  , opSymbol
  ) where

-- | Nombre de variable. El parser garantiza @^[a-z_][A-Za-z0-9_]*$@.
type Name = String

-- | τ ::= Int | Bool | String | τ → τ
data Type
  = TInt
  | TBool
  | TString
  | TArrow Type Type
  deriving (Show, Eq)

-- | Valores que puede llevar un constructor 'Literal'.
data LiteralValue
  = VInt Int
  | VBool Bool
  | VString String
  deriving (Show, Eq)

-- | Operadores binarios: comparación y lógicos.
data BinOp
  = Gt
  | Lt
  | Gte
  | Lte
  | Eq
  | And
  | Or
  deriving (Show, Eq, Enum, Bounded)

-- | e ::= Literal | Var | BinaryOp | IfThenElse | Lam | App
data Expr
  = Literal LiteralValue
  | Var Name
  | BinaryOp BinOp Expr Expr
  | IfThenElse Expr Expr Expr
  | Lam Name Type Expr
  | App Expr Expr
  deriving (Show, Eq)

-- | Raíz de la salida del LLM: @{"expr": ...}@.
newtype Program = Program Expr
  deriving (Show, Eq)

-- | Int, Bool y String son tipos base; las flechas no.
isBase :: Type -> Bool
isBase (TArrow _ _) = False
isBase _ = True

literalType :: LiteralValue -> Type
literalType (VInt _) = TInt
literalType (VBool _) = TBool
literalType (VString _) = TString

-- | Tipo en notación del contrato: @Int@, @(Int -> Bool) -> Bool@.
renderType :: Type -> String
renderType TInt = "Int"
renderType TBool = "Bool"
renderType TString = "String"
renderType (TArrow a b) = domain a ++ " -> " ++ renderType b
  where
    domain t@(TArrow _ _) = "(" ++ renderType t ++ ")"
    domain t = renderType t

-- | Símbolo del operador tal como aparece en el JSON.
opSymbol :: BinOp -> String
opSymbol Gt = ">"
opSymbol Lt = "<"
opSymbol Gte = ">="
opSymbol Lte = "<="
opSymbol Eq = "=="
opSymbol And = "AND"
opSymbol Or = "OR"
