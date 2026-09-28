{-# LANGUAGE OverloadedStrings #-}

module Main where

import Types
import Typecheck
import Data.Aeson
import Data.Aeson.Types (Parser)
import qualified Data.ByteString.Lazy as B
import qualified Data.Map.Strict as Map
import qualified Data.Text as T
import System.IO (stdin, stdout)

-- Estructura de entrada esperada desde Python
data InputPayload = InputPayload
  { inputAST :: Expr
  , inputEnv :: Map.Map String Type
  } deriving (Show)

instance FromJSON InputPayload where
  parseJSON = withObject "InputPayload" $ \o -> do
    ast <- o .: "ast"
    envMap <- o .:? "env" .!= Map.empty
    return $ InputPayload ast envMap

-- Estructura de diagnóstico de salida hacia Python (alineada a OutputRecordSchema)
data ValidationResult = ValidationResult
  { static_validation_passed :: Bool
  , static_error_message      :: Maybe String
  , inferred_type            :: Maybe String
  } deriving (Show)

instance ToJSON ValidationResult where
  toJSON (ValidationResult passed err mType) = object
    [ "static_validation_passed" .= passed
    , "static_error_message"      .= err
    , "inferred_type"            .= mType
    ]

main :: IO ()
main = do
  inputBytes <- B.hGetContents stdin
  case eitherDecode inputBytes of
    Left parseErr -> do
      let res = ValidationResult False (Just $ "Error de parseo Aeson: " ++ parseErr) Nothing
      B.putStr (encode res)
    Right (InputPayload expr env) ->
      case tcExpr env expr of
        Left typeErr -> do
          let res = ValidationResult False (Just $ renderTypeError typeErr) Nothing
          B.putStr (encode res)
        Right inferredT -> do
          let res = ValidationResult True Nothing (Just $ show inferredT)
          B.putStr (encode res)
