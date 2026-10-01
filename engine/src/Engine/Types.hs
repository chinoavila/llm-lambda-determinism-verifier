-- | Tipos del AST del DSL STLC.
--
-- Gramática acordada en @contracts/ast-schema.json@ (reglas en
-- @contracts/README.md@):
--   Tipos        τ ::= Int | Decimal | Bool | String | τ → τ
--   Expresiones  e ::= Literal | Var | UnaryOp | BinaryOp | In | IfThenElse | Lam | App
module Engine.Types
  ( Name
  , Type (..)
  , LiteralValue (..)
  , UnOp (..)
  , BinOp (..)
  , Expr (..)
  , Program (..)
  , isBase
  , isNumeric
  , literalType
  , renderType
  , opSymbol
  , unOpSymbol
  ) where

-- FP[Tipos]
-- | Nombre de variable. El parser garantiza @^[a-z_][A-Za-z0-9_]*$@.
type Name = String

-- Equivale a las reglas BaseType y Type de contracts/ast-schema.json.
-- TInt, TDecimal, TBool y TString son los cuatro tipos básicos
-- ("Int", "Decimal", "Bool" y "String" en el JSON).
-- TArrow a b es el tipo de función { "from": a, "to": b }.
-- FP[Tipos] FP[Tipos algebraicos]
-- | τ ::= Int | Decimal | Bool | String | τ → τ
data Type
  = TInt
  | TDecimal
  | TBool
  | TString
  | TArrow Type Type
  deriving (Show, Eq)

-- | Valores que puede llevar un constructor 'Literal'. 'VDecimal' es un
-- racional exacto: @0.1 + 0.2 == 0.3@ es verdadero.
data LiteralValue
  = VInt Int
  | VDecimal Rational
  | VBool Bool
  | VString String
  deriving (Show, Eq)

-- | Operadores unarios.
data UnOp = Not
  deriving (Show, Eq, Enum, Bounded)

-- FP[Clases]
-- | Operadores binarios: aritméticos, de comparación y lógicos.
data BinOp
  = Add
  | Sub
  | Mul
  | Div
  | Mod
  | Gt
  | Lt
  | Gte
  | Lte
  | Eq
  | Neq
  | And
  | Or
  deriving (Show, Eq, Enum, Bounded)


-- Equivale a la regla Expr de contracts/ast-schema.json: una expresión es
-- una de estas 8 formas. Los campos del JSON corresponden, en orden, a los
-- datos que lleva cada forma:
--   Literal    -> value y value_type (juntos en LiteralValue)
--   Var        -> name
--   UnaryOp    -> op, operand
--   BinaryOp   -> op, left, right
--   In         -> value, options
--   IfThenElse -> condition, then, else
--   Lam        -> param, param_type, body
--   App        -> fn, arg
-- Explicación de cada forma: docs/guia-ast-schema.md.
-- FP[Tipos algebraicos] FP[Funciones lambda]
-- | e ::= Literal | Var | UnaryOp | BinaryOp | In | IfThenElse | Lam | App
data Expr
  = Literal LiteralValue
  | Var Name
  | UnaryOp UnOp Expr
  | BinaryOp BinOp Expr Expr
  | In Expr [Expr] -- ^ valor y opciones (lista no vacía, la garantiza el parser)
  | IfThenElse Expr Expr Expr
  | Lam Name Type Expr
  | App Expr Expr
  deriving (Show, Eq)

-- FP[Tipos]
-- | Raíz de la salida del LLM: @{"expr": ...}@.
newtype Program = Program Expr
  deriving (Show, Eq)

-- FP[Patrones irrefutables]
-- | Int, Decimal, Bool y String son tipos base; las flechas no.
isBase :: Type -> Bool
isBase (TArrow _ _) = False
isBase _ = True

-- | Int y Decimal: los tipos que admiten aritmética y comparaciones de orden.
isNumeric :: Type -> Bool
isNumeric t = t == TInt || t == TDecimal

-- FP[Igualaciones]
-- | Tipo base asociado a un literal; no inspecciona cómo se usa en la expresión.
literalType :: LiteralValue -> Type
literalType (VInt _) = TInt
literalType (VDecimal _) = TDecimal
literalType (VBool _) = TBool
literalType (VString _) = TString

-- FP[Recursión] FP[Inferencia de tipos]
-- | Tipo en notación del contrato: @Int@, @(Int -> Bool) -> Bool@.
renderType :: Type -> String
renderType TInt = "Int"
renderType TDecimal = "Decimal"
renderType TBool = "Bool"
renderType TString = "String"
renderType (TArrow a b) = domain a ++ " -> " ++ renderType b
  where
    domain t@(TArrow _ _) = "(" ++ renderType t ++ ")"
    domain t = renderType t

-- FP[Patrones constantes]
-- | Símbolo del operador tal como aparece en el JSON.
opSymbol :: BinOp -> String
opSymbol Add = "+"
opSymbol Sub = "-"
opSymbol Mul = "*"
opSymbol Div = "/"
opSymbol Mod = "%"
opSymbol Gt = ">"
opSymbol Lt = "<"
opSymbol Gte = ">="
opSymbol Lte = "<="
opSymbol Eq = "=="
opSymbol Neq = "!="
opSymbol And = "AND"
opSymbol Or = "OR"

-- | Nombre estable del operador unario en el AST JSON.
unOpSymbol :: UnOp -> String
unOpSymbol Not = "NOT"
