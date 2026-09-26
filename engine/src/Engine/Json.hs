{-# LANGUAGE OverloadedStrings #-}
{-# OPTIONS_GHC -Wno-orphans #-}

-- | Frontera de entrada: JSON → ADT, según @contracts/ast-schema.json@.
--
-- Las instancias 'FromJSON' viven acá (y no en "Engine.Types") para que el
-- ADT no dependa del formato de serialización; de ahí el @-Wno-orphans@.
module Engine.Json
  ( ParseError (..)
  , EnvError (..)
  , parseProgram
  , envFromJSON
  , parseErrorCode
  , envErrorMessage
  ) where

import Control.Monad (unless)
import Data.Aeson (FromJSON (..), Object, Value (..), eitherDecode, withObject, (.:))
import qualified Data.Aeson.Key as Key
import qualified Data.Aeson.KeyMap as KeyMap
import Data.Aeson.Types (Parser, parseEither, parseMaybe)
import qualified Data.ByteString.Lazy as BL
import Data.Char (isAsciiLower, isAsciiUpper, isDigit)
import Data.List (isInfixOf)

import Engine.Env (Env)
import Engine.Types

-- FP[Tipos algebraicos]
-- | Errores de la etapa @parse@. El texto es el mensaje de aeson, que incluye
-- la ruta del nodo (por ejemplo @$.expr.left@).
data ParseError
  = MalformedJson String
  | InvalidAst String
  | LiteralTypeMismatch String
  deriving (Show, Eq)

-- | Errores de @--env@: son errores de uso (exit 64), no del LLM.
data EnvError
  = EnvNotObject
  | InvalidEnvName Name
  | InvalidEnvValue Name
  deriving (Show, Eq)

parseErrorCode :: ParseError -> String
parseErrorCode (MalformedJson _) = "MALFORMED_JSON"
parseErrorCode (InvalidAst _) = "INVALID_AST"
parseErrorCode (LiteralTypeMismatch _) = "LITERAL_TYPE_MISMATCH"

envErrorMessage :: EnvError -> String
envErrorMessage EnvNotObject = "--env debe ser un objeto JSON"
envErrorMessage (InvalidEnvName x) = "nombre inválido en --env: " ++ show x
envErrorMessage (InvalidEnvValue x) =
  "valor de " ++ show x ++ " en --env: se esperaba entero de 64 bits, booleano o cadena"

-- FP[Funciones puras] FP[Composición] FP[Orden superior] FP[Excepcioness] FP[Inferencia de tipos]
-- | Primero exige JSON sintácticamente válido; después, la forma del AST.
parseProgram :: BL.ByteString -> Either ParseError Program
parseProgram bytes = case eitherDecode bytes of
  Left msg -> Left (MalformedJson msg)
  Right value -> either (Left . classify) Right (parseEither parseJSON value)
  where
    classify msg
      | literalMismatchTag `isInfixOf` msg = LiteralTypeMismatch msg
      | otherwise = InvalidAst msg

-- | aeson solo transporta errores como texto: esta marca distingue un
-- literal con @value@ y @value_type@ inconsistentes de una forma inválida.
literalMismatchTag :: String
literalMismatchTag = "LITERAL_TYPE_MISMATCH"

-- FP[Orden superior] FP[Tuplas] FP[Excepcioness]
-- | Deduce los datos del caso desde @--env@. Γ es @fmap literalType@ del
-- resultado: el tipo sale del valor, nunca de cómo lo usa la regla.
envFromJSON :: Value -> Either EnvError (Env LiteralValue)
envFromJSON (Object o) = traverse entry (KeyMap.toList o)
  where
    entry (k, v)
      | not (validName x) = Left (InvalidEnvName x)
      | otherwise = maybe (Left (InvalidEnvValue x)) (Right . (,) x) (envValue v)
      where
        x = Key.toString k
envFromJSON _ = Left EnvNotObject

envValue :: Value -> Maybe LiteralValue
envValue v@(Number _) = VInt <$> parseMaybe parseJSON v
envValue (Bool b) = Just (VBool b)
envValue v@(String _) = VString <$> parseMaybe parseJSON v
envValue _ = Nothing

-- FP[Patrones de listas] FP[map/filter/fold] FP[Inferencia de tipos] FP[Funciones totales]
-- | @^[a-z_][A-Za-z0-9_]*$@
validName :: Name -> Bool
validName [] = False
validName (c : cs) = (isAsciiLower c || c == '_') && all rest cs
  where
    rest x = isAsciiLower x || isAsciiUpper x || isDigit x || x == '_'

-- FP[Listas por comprensión] FP[null]
-- | Rechaza cualquier clave que el contrato no permita en el nodo.
onlyKeys :: [String] -> Object -> Parser ()
onlyKeys allowed o =
  unless (null extra) (fail ("claves no permitidas: " ++ show extra))
  where
    extra = [k | k <- map Key.toString (KeyMap.keys o), k `notElem` allowed]

nameField :: Object -> Key.Key -> Parser Name
nameField o k = do
  x <- o .: k
  unless (validName x) (fail ("nombre inválido: " ++ show x))
  pure x

-- FP[Clases] FP[Funciones anónimas]
instance FromJSON Program where
  parseJSON = withObject "Program" $ \o -> do
    onlyKeys ["expr"] o
    Program <$> o .: "expr"

-- FP[Clases] FP[Patrones constantes]
instance FromJSON Type where
  parseJSON (String s) = case s of
    "Int" -> pure TInt
    "Bool" -> pure TBool
    "String" -> pure TString
    _ -> fail ("tipo desconocido: " ++ show s)
  parseJSON v = withObject "Type" arrow v
    where
      arrow o = do
        onlyKeys ["from", "to"] o
        TArrow <$> o .: "from" <*> o .: "to"

-- FP[Listas por comprensión] FP[Polimorfismo]
instance FromJSON BinOp where
  parseJSON v = do
    s <- parseJSON v :: Parser String
    case lookup s [(opSymbol op, op) | op <- [minBound .. maxBound]] of
      Just op -> pure op
      Nothing -> fail ("operador desconocido: " ++ show s)

-- FP[Clases] FP[Patrones constantes]
instance FromJSON Expr where
  parseJSON = withObject "Expr" $ \o -> do
    tag <- o .: "type" :: Parser String
    case tag of
      "Literal" -> do
        onlyKeys ["type", "value", "value_type"] o
        Literal <$> literal o
      "Var" -> do
        onlyKeys ["type", "name"] o
        Var <$> nameField o "name"
      "BinaryOp" -> do
        onlyKeys ["type", "op", "left", "right"] o
        BinaryOp <$> o .: "op" <*> o .: "left" <*> o .: "right"
      "IfThenElse" -> do
        onlyKeys ["type", "condition", "then", "else"] o
        IfThenElse <$> o .: "condition" <*> o .: "then" <*> o .: "else"
      "Lam" -> do
        onlyKeys ["type", "param", "param_type", "body"] o
        Lam <$> nameField o "param" <*> o .: "param_type" <*> o .: "body"
      "App" -> do
        onlyKeys ["type", "fn", "arg"] o
        App <$> o .: "fn" <*> o .: "arg"
      _ -> fail ("tipo de nodo desconocido: " ++ show tag)

-- | Un @value@ que no es entero, booleano ni cadena es forma inválida; uno
-- válido pero distinto de @value_type@ es 'LiteralTypeMismatch'.
literal :: Object -> Parser LiteralValue
literal o = do
  declared <- o .: "value_type"
  unless (isBase declared) (fail "value_type debe ser Int, Bool o String")
  raw <- o .: "value"
  actual <- case raw of
    Number _ -> VInt <$> parseJSON raw
    Bool b -> pure (VBool b)
    String _ -> VString <$> parseJSON raw
    _ -> fail "value debe ser entero, booleano o cadena"
  unless (literalType actual == declared) $
    fail
      ( literalMismatchTag ++ ": value es "
          ++ renderType (literalType actual)
          ++ " pero value_type es "
          ++ renderType declared
      )
  pure actual
