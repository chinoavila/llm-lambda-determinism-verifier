{-# LANGUAGE OverloadedStrings #-}

module Types where

import Data.Aeson
import Data.Aeson.Types (Parser)
import qualified Data.Text as T
import Control.Applicative ((<|>))

-- ============================================================================
-- 1. MODELADO DEL SISTEMA DE TIPOS (Type)
-- ============================================================================

data BaseType = TDouble | TInt | TBool | TString
  deriving (Show, Eq)

data Type
  = Base BaseType
  | Arrow Type Type
  deriving (Show, Eq)

instance FromJSON Type where
  parseJSON = withObject "Type" $ \o -> do
    kind <- o .: "kind" :: Parser T.Text
    case kind of
      "Base" -> do
        name <- o .: "name" :: Parser T.Text
        case name of
          "Double" -> return $ Base TDouble
          "Int"    -> return $ Base TInt
          "Bool"   -> return $ Base TBool
          "String" -> return $ Base TString
          other    -> fail $ "Tipo base no soportado: " ++ T.unpack other
      "Arrow" -> do
        fromT <- o .: "from"
        toT   <- o .: "to"
        return $ Arrow fromT toT
      other -> fail $ "Kind desconocido: " ++ T.unpack other

-- ============================================================================
-- 2. VALORES PRIMITIVOS DEL DOMINIO (Val) Y OPERADORES BINARIOS
-- ============================================================================

data Val
  = VLDouble Double
  | VLInt Integer
  | VLBool Bool
  | VLString T.Text
  deriving (Show, Eq)

data Op
  = Add | Sub | Mul | Div
  | Gt  | Lt  | Gte | Lte | EqOp
  | And | Or
  deriving (Show, Eq)

parseOp :: T.Text -> Parser Op
parseOp "+"  = return Add
parseOp "-"  = return Sub
parseOp "*"  = return Mul
parseOp "/"  = return Div
parseOp ">"  = return Gt
parseOp "<"  = return Lt
parseOp ">=" = return Gte
parseOp "<=" = return Lte
parseOp "==" = return EqOp
parseOp "&&" = return And
parseOp "||" = return Or
parseOp op   = fail $ "Operador no reconocido: " ++ T.unpack op

-- ============================================================================
-- 3. MODELADO DE EXPRESIONES (Expr / AST)
-- ============================================================================

data Expr
  = Var String
  | Literal Type Val
  | Lam String Type Expr
  | App Expr Expr
  | BinaryOp Op Expr Expr
  | IfThenElse Expr Expr Expr
  deriving (Show, Eq)

-- Deserializador de Literales tipados de forma determinista
parseLiteral :: Object -> Parser (Type, Val)
parseLiteral o = do
  t <- o .: "type"
  case t of
    Base TInt -> do
      val <- o .: "value" :: Parser Integer
      return (t, VLInt val)
    Base TDouble -> do
      -- Admite notación con o sin punto decimal
      val <- (o .: "value" :: Parser Double)
         <|> (fromIntegral <$> (o .: "value" :: Parser Integer))
      return (t, VLDouble val)
    Base TBool -> do
      val <- o .: "value" :: Parser Bool
      return (t, VLBool val)
    Base TString -> do
      val <- o .: "value" :: Parser T.Text
      return (t, VLString val)
    Arrow _ _ -> fail "Los literales no pueden tener tipo funcional (Arrow)."

instance FromJSON Expr where
  parseJSON = withObject "Expr" $ \o -> do
    tag <- o .: "tag" :: Parser T.Text
    case tag of
      "Var" -> do
        name <- o .: "name"
        return $ Var name

      "Literal" -> do
        (t, val) <- parseLiteral o
        return $ Literal t val

      "Lam" -> do
        param     <- o .: "param"
        paramType <- o .: "param_type"
        body      <- o .: "body"
        return $ Lam param paramType body

      "App" -> do
        fn  <- o .: "func"
        arg <- o .: "arg"
        return $ App fn arg

      "BinaryOp" -> do
        opStr <- o .: "op"
        op    <- parseOp opStr
        left  <- o .: "left"
        right <- o .: "right"
        return $ BinaryOp op left right

      "IfThenElse" -> do
        c <- o .: "cond"
        t <- o .: "then"
        e <- o .: "else"
        return $ IfThenElse c t e

      other -> fail $ "Tag de expresion no reconocido: " ++ T.unpack other
