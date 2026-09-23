-- | Tipos del AST del DSL STLC.
--
-- Gramática acordada en specs/tech-stack.md (Día 0):
--   Tipos        τ ::= Int | Bool | String | τ → τ
--   Expresiones  e ::= Literal | Var | BinaryOp | IfThenElse | Lam | App
--
-- PENDIENTE: falta typechecker, evaluador, y la instancia 'FromJSON' contra
-- @contracts/ast-schema.json@ (todavía placeholder, a cerrar entre los 3 devs).
module Engine.Types
  ( Type (..)
  , LiteralValue (..)
  , BinOp (..)
  , Expr (..)
  ) where

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
  deriving (Show, Eq)

-- | e ::= Literal | Var | BinaryOp | IfThenElse | Lam | App
data Expr
  = Literal LiteralValue
  | Var String
  | BinaryOp BinOp Expr Expr
  | IfThenElse Expr Expr Expr
  | Lam String Type Expr
  | App Expr Expr
  deriving (Show, Eq)
