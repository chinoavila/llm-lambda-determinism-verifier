module Main (main) where

import Engine.Types (BinOp (Gt), Expr (BinaryOp, Literal), LiteralValue (VInt))

-- | PLACEHOLDER: leer JSON de stdin, deserializar a 'Expr', tipar, evaluar,
-- e imprimir el veredicto en stdout con código de salida estable.
-- Reemplazar según el contrato de CLI acordado (ver specs/roadmap.md).
main :: IO ()
main = print example
  where
    -- e = 5 > 3
    example = BinaryOp Gt (Literal (VInt 5)) (Literal (VInt 3))
