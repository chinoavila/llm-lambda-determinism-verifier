{-# LANGUAGE OverloadedStrings #-}

module Typecheck where

import Types
import qualified Data.Map.Strict as Map
import Data.Map.Strict (Map)

type TypeEnv = Map String Type

data TypeError
  = UnboundVariable String
  | TypeMismatch { expected :: Type, actual :: Type, context :: String }
  | NotAFunction { actualType :: Type, exprContext :: String }
  | InvalidBinaryOp { op :: Op, leftType :: Type, rightType :: Type }
  | LiteralMismatch { declaredType :: Type, actualValue :: Val }
  deriving (Show, Eq)

renderTypeError :: TypeError -> String
renderTypeError (UnboundVariable var) =
  "Error de Scope: Variable libre no declarada '" ++ var ++ "'"
renderTypeError (TypeMismatch exp act ctx) =
  "Discrepancia de Tipos en " ++ ctx ++ ": se esperaba " ++ show exp ++ " pero se obtuvo " ++ show act
renderTypeError (NotAFunction act ctx) =
  "Error de Aplicación en " ++ ctx ++ ": se intentó aplicar un término de tipo no funcional " ++ show act
renderTypeError (InvalidBinaryOp op l r) =
  "Operación Binaria Inválida (" ++ show op ++ "): tipos incompatibles left=" ++ show l ++ ", right=" ++ show r
renderTypeError (LiteralMismatch dt val) =
  "Inconsistencia en Literal: el valor " ++ show val ++ " no corresponde al tipo " ++ show dt

tcExpr :: TypeEnv -> Expr -> Either TypeError Type
tcExpr env expr = case expr of

  Var x ->
    case Map.lookup x env of
      Just t  -> Right t
      Nothing -> Left $ UnboundVariable x

  Literal t v ->
    case (t, v) of
      (Base TDouble, VLDouble _) -> Right t
      (Base TInt,    VLInt _)    -> Right t
      (Base TBool,   VLBool _)   -> Right t
      (Base TString, VLString _) -> Right t
      _                          -> Left $ LiteralMismatch t v

  IfThenElse c th el -> do
    tCond <- tcExpr env c
    case tCond of
      Base TBool -> do
        tThen <- tcExpr env th
        tElse <- tcExpr env el
        if tThen == tElse
          then Right tThen
          else Left $ TypeMismatch { expected = tThen, actual = tElse, context = "ramas Then y Else de IfThenElse" }
      other -> Left $ TypeMismatch { expected = Base TBool, actual = other, context = "condición de IfThenElse" }

  BinaryOp op l r -> do
    tLeft  <- tcExpr env l
    tRight <- tcExpr env r
    case op of
      _ | op `elem` [Add, Sub, Mul, Div] ->
        if (tLeft == Base TDouble && tRight == Base TDouble) ||
           (tLeft == Base TInt    && tRight == Base TInt)
          then Right tLeft
          else Left $ InvalidBinaryOp op tLeft tRight

      _ | op `elem` [Gt, Lt, Gte, Lte] ->
        if (tLeft == Base TDouble && tRight == Base TDouble) ||
           (tLeft == Base TInt    && tRight == Base TInt)
          then Right (Base TBool)
          else Left $ InvalidBinaryOp op tLeft tRight

      EqOp ->
        if tLeft == tRight
          then Right (Base TBool)
          else Left $ InvalidBinaryOp op tLeft tRight

      _ | op `elem` [And, Or] ->
        if tLeft == Base TBool && tRight == Base TBool
          then Right (Base TBool)
          else Left $ InvalidBinaryOp op tLeft tRight

      _ -> Left $ InvalidBinaryOp op tLeft tRight

  Lam x paramType body -> do
    let extendedEnv = Map.insert x paramType env
    bodyType <- tcExpr extendedEnv body
    Right $ Arrow paramType bodyType

  App f arg -> do
    tFunc <- tcExpr env f
    tArg  <- tcExpr env arg
    case tFunc of
      Arrow tFrom tTo ->
        if tFrom == tArg
          then Right tTo
          else Left $ TypeMismatch { expected = tFrom, actual = tArg, context = "argumento de función en App" }
      notFunc -> Left $ NotAFunction { actualType = notFunc, exprContext = "posición de función en App" }
