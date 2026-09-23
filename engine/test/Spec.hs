module Main (main) where

import Test.Hspec

import Engine.Types (Expr (Literal), LiteralValue (VInt))

-- | PLACEHOLDER: reemplazar por los tests reales del typechecker/evaluador
-- (un caso que debe aceptar y uno que debe rechazar, por cada regla de tipado).
main :: IO ()
main = hspec $
  describe "Engine.Types" $
    it "placeholder: el esqueleto compila y corre" $
      Literal (VInt 0) `shouldBe` Literal (VInt 0)
