-- | Tipos del AST del DSL STLC.
--
-- PLACEHOLDER: este ADT es un stub para que el proyecto compile desde el día 0.
-- Reemplazar por la gramática real acordada en @contracts/ast-schema.json@
-- (ver specs/roadmap.md, día 0-1, dueño: dev de engine/).
module Engine.Types
  ( Expr (..)
  ) where

data Expr
  = Literal Int
  deriving (Show, Eq)
