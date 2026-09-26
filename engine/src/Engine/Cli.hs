{-# LANGUAGE OverloadedStrings #-}

-- | Contrato CLI del engine (@contracts/README.md@ §2), como función pura:
-- argumentos + bytes de stdin → código de salida, stdout y stderr.
-- "Main" solo hace el IO alrededor de 'run'.
module Engine.Cli
  ( Options (..)
  , Verdict (..)
  , Response (..)
  , parseArgs
  , decodeEnv
  , validate
  , verdictExit
  , encodeVerdict
  , encodeGamma
  , run
  ) where

import Data.Aeson (Value, eitherDecode)
import qualified Data.Aeson.Encoding as E
import qualified Data.Aeson.Key as Key
import Data.Bifunctor (first)
import qualified Data.ByteString.Builder as B
import qualified Data.ByteString.Lazy as BL
import Data.List (sortOn)
import System.Exit (ExitCode (..))

import Engine.Env (Env, emptyEnv)
import Engine.Eval (evalErrorMessage, evalProgram, EvalError)
import Engine.Json
import Engine.TypeCheck
import Engine.Types

-- | @engine [--env '<objeto JSON>'] [--print-gamma]@
data Options = Options
  { optEnv :: Maybe String
  , optPrintGamma :: Bool
  }
  deriving (Show, Eq)

-- FP[Tipos algebraicos]
-- | Desenlace de la validación. Reutiliza los errores tipados de cada etapa.
data Verdict
  = Executed LiteralValue
  | BlockedParse ParseError
  | BlockedCheck CheckError
  deriving (Show, Eq)

data Response = Response
  { resExit :: ExitCode
  , resStdout :: BL.ByteString -- ^ vacío en los exit 64 y 70
  , resStderr :: String -- ^ diagnóstico libre; vacío si no hay nada que decir
  }
  deriving (Show, Eq)

-- FP[Recursión] FP[Patrones de listas]
-- | Cada opción se acepta una sola vez; cualquier otra cosa es error de uso.
parseArgs :: [String] -> Either String Options
parseArgs = go (Options Nothing False)
  where
    go opts [] = Right opts
    go opts ("--print-gamma" : rest)
      | not (optPrintGamma opts) = go opts {optPrintGamma = True} rest
    go opts ("--env" : raw : rest)
      | Nothing <- optEnv opts = go opts {optEnv = Just raw} rest
    go _ (arg : _) = Left ("argumento inválido o repetido: " ++ arg)

-- | Sin @--env@, los datos del caso son @{}@.
decodeEnv :: Maybe String -> Either String (Env LiteralValue)
decodeEnv Nothing = Right emptyEnv
decodeEnv (Just raw) = do
  value <- first (const "--env no es JSON válido") (eitherDecode (utf8 raw) :: Either String Value)
  first envErrorMessage (envFromJSON value)

-- FP[Funciones puras] FP[Composición]
-- | parse → scope → typecheck → execution. Cada etapa corta en su primer
-- error. 'Left' solo si el evaluador se atasca sobre un programa verificado:
-- eso es un bug del motor, no del LLM.
validate :: Env LiteralValue -> BL.ByteString -> Either EvalError Verdict
validate env input = case parseProgram input of
  Left err -> Right (BlockedParse err)
  Right prog -> case checkProgram (typesOf env) prog of
    Left err -> Right (BlockedCheck err)
    Right _ -> Executed <$> evalProgram env prog

-- FP[Polimorfismo]
-- | Γ se deduce de los valores del caso.
typesOf :: Env LiteralValue -> Env Type
typesOf = map (fmap literalType)

-- FP[Patrones constantes]
verdictExit :: Verdict -> ExitCode
verdictExit (Executed _) = ExitSuccess
verdictExit (BlockedParse _) = ExitFailure 1
verdictExit (BlockedCheck err) = case errorStage err of
  Scope -> ExitFailure 2
  TypeCheck -> ExitFailure 3

-- | Una línea conforme a @engine-verdict-schema.json@. Las claves van en el
-- orden del contrato (no alfabético), así que se arma con 'E.pairs'.
encodeVerdict :: Verdict -> BL.ByteString
encodeVerdict v = line $ case v of
  Executed lit -> verdict "executed" "execution" (result lit) E.null_
  BlockedParse err ->
    verdict "blocked" "parse" E.null_ (errorObj (parseErrorCode err) (parseErrorMessage err))
  BlockedCheck err ->
    verdict "blocked" (stageName (errorStage err)) E.null_ (errorObj (errorCode err) (errorMessage err))
  where
    verdict outcome stage res err =
      E.pairs
        ( E.pair "outcome" (E.string outcome)
            <> E.pair "stage" (E.string stage)
            <> E.pair "result" res
            <> E.pair "error" err
        )
    result lit =
      E.pairs (E.pair "type" (E.string (renderType (literalType lit))) <> E.pair "value" (literalJson lit))
    errorObj code msg = E.pairs (E.pair "code" (E.string code) <> E.pair "message" (E.string msg))
    stageName Scope = "scope"
    stageName TypeCheck = "typecheck"

literalJson :: LiteralValue -> E.Encoding
literalJson (VInt n) = E.int n
literalJson (VBool b) = E.bool b
literalJson (VString s) = E.string s

-- FP[map/filter/fold] FP[Orden superior]
-- | Γ como objeto @{nombre: tipo}@ con claves en orden alfabético.
encodeGamma :: Env Type -> BL.ByteString
encodeGamma gamma = line (E.pairs (foldMap entry (sortOn fst gamma)))
  where
    entry (x, t) = E.pair (Key.fromString x) (E.string (renderType t))

-- FP[Evaluación perezosa] FP[Condicionales]
-- | Con @--print-gamma@, 'run' nunca mira @input@: como "Main" lo lee de
-- forma perezosa, stdin ni siquiera se consume.
run :: [String] -> BL.ByteString -> Response
run args input = case setup of
  Left msg -> Response (ExitFailure 64) "" (msg ++ "\n" ++ usage)
  Right (opts, env)
    | optPrintGamma opts -> Response ExitSuccess (encodeGamma (typesOf env)) ""
    | otherwise -> case validate env input of
        Left err -> Response (ExitFailure 70) "" ("error interno: " ++ evalErrorMessage err)
        Right v -> Response (verdictExit v) (encodeVerdict v) ""
  where
    setup = do
      opts <- parseArgs args
      env <- decodeEnv (optEnv opts)
      pure (opts, env)
    usage = "uso: engine [--env '<objeto JSON>'] [--print-gamma] < respuesta_del_llm"

line :: E.Encoding -> BL.ByteString
line enc = E.encodingToLazyByteString enc <> "\n"

utf8 :: String -> BL.ByteString
utf8 = B.toLazyByteString . B.stringUtf8
