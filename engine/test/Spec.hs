{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Data.Aeson (Value, eitherDecode, withObject, (.:))
import Data.Aeson.Types (Parser, parseEither)
import qualified Data.ByteString.Builder as B
import qualified Data.ByteString.Lazy as BL
import Test.Hspec
import Test.QuickCheck

import Engine.Env (Env, emptyEnv, extend, lookupVar)
import Engine.Json
import Engine.TypeCheck
import Engine.Types

main :: IO ()
main = hspec $ do
  envSpec
  jsonSpec
  typeCheckSpec
  fixturesSpec

-- * Helpers

utf8 :: String -> BL.ByteString
utf8 = B.toLazyByteString . B.stringUtf8

parse :: String -> Either ParseError Program
parse = parseProgram . utf8

int :: Int -> Expr
int = Literal . VInt

bool :: Bool -> Expr
bool = Literal . VBool

str :: String -> Expr
str = Literal . VString

-- | Γ de los fixtures de crédito.
gamma :: Env Type
gamma = [("credit_score", TInt), ("has_defaults", TBool), ("customer_tier", TString)]

-- | Solo el código de error, para comparar sin depender del mensaje.
codeOf :: Either ParseError a -> Either String a
codeOf = either (Left . parseErrorCode) Right

checkCode :: Expr -> Either String Type
checkCode = either (Left . errorCode) Right . checkProgram gamma . Program

-- * Entorno

envSpec :: Spec
envSpec = describe "Engine.Env" $ do
  it "un binding nuevo oculta al anterior sin modificar el original" $ do
    let outer = extend "x" TInt emptyEnv
        inner = extend "x" TBool outer
    lookupVar "x" inner `shouldBe` Just TBool
    lookupVar "x" outer `shouldBe` Just TInt

  it "lookupVar encuentra lo que extend agregó" $
    property $ \x (n :: Int) env ->
      lookupVar x (extend x n env) === Just n

-- * JSON → ADT

jsonSpec :: Spec
jsonSpec = describe "Engine.Json" $ do
  describe "parseProgram" $ do
    it "parsea todos los constructores y tipos flecha" $
      parse
        "{\"expr\":{\"type\":\"App\",\"fn\":{\"type\":\"Lam\",\"param\":\"f\",\
        \\"param_type\":{\"from\":\"Int\",\"to\":\"Bool\"},\"body\":{\"type\":\"IfThenElse\",\
        \\"condition\":{\"type\":\"BinaryOp\",\"op\":\"OR\",\"left\":{\"type\":\"Literal\",\
        \\"value\":true,\"value_type\":\"Bool\"},\"right\":{\"type\":\"Var\",\"name\":\"x\"}},\
        \\"then\":{\"type\":\"Literal\",\"value\":\"si\",\"value_type\":\"String\"},\
        \\"else\":{\"type\":\"Literal\",\"value\":-3,\"value_type\":\"Int\"}}},\
        \\"arg\":{\"type\":\"Var\",\"name\":\"g\"}}}"
        `shouldBe` Right
          ( Program
              ( App
                  ( Lam "f" (TArrow TInt TBool)
                      (IfThenElse (BinaryOp Or (bool True) (Var "x")) (str "si") (int (-3)))
                  )
                  (Var "g")
              )
          )

    it "acepta los siete operadores" $
      let src op = "{\"expr\":{\"type\":\"BinaryOp\",\"op\":\"" ++ opSymbol op ++ "\",\
                   \\"left\":{\"type\":\"Var\",\"name\":\"a\"},\"right\":{\"type\":\"Var\",\"name\":\"b\"}}}"
       in [parse (src op) | op <- [minBound .. maxBound]]
            `shouldBe` [Right (Program (BinaryOp op (Var "a") (Var "b"))) | op <- [minBound .. maxBound]]

    it "MALFORMED_JSON si no es JSON" $ do
      codeOf (parse "{\"expr\":") `shouldBe` Left "MALFORMED_JSON"
      codeOf (parse "") `shouldBe` Left "MALFORMED_JSON"

    it "INVALID_AST ante formas que el contrato no permite" $
      mapM_
        (\src -> codeOf (parse src) `shouldBe` Left "INVALID_AST")
        [ "{\"type\":\"Var\",\"name\":\"x\"}" -- falta la raíz expr
        , "{\"expr\":{\"type\":\"Var\",\"name\":\"x\"},\"extra\":1}" -- clave extra en la raíz
        , "{\"expr\":{\"type\":\"Var\",\"name\":\"x\",\"value_type\":\"Int\"}}" -- clave extra en un nodo
        , "{\"expr\":{\"type\":\"Let\",\"name\":\"x\"}}" -- constructor inexistente
        , "{\"expr\":{\"type\":\"BinaryOp\",\"op\":\"+\",\"left\":{\"type\":\"Var\",\"name\":\"a\"},\"right\":{\"type\":\"Var\",\"name\":\"b\"}}}"
        , "{\"expr\":{\"type\":\"Var\"}}" -- campo faltante
        , "{\"expr\":{\"type\":\"Var\",\"name\":\"Credit\"}}" -- nombre fuera del patrón
        , "{\"expr\":{\"type\":\"Literal\",\"value\":7.5,\"value_type\":\"Int\"}}" -- decimal
        , "{\"expr\":{\"type\":\"Literal\",\"value\":null,\"value_type\":\"Int\"}}"
        , "{\"expr\":{\"type\":\"Literal\",\"value\":1,\"value_type\":\"Float\"}}"
        , "{\"expr\":{\"type\":\"Lam\",\"param\":\"x\",\"param_type\":{\"from\":\"Int\"},\"body\":{\"type\":\"Var\",\"name\":\"x\"}}}"
        ]

    it "LITERAL_TYPE_MISMATCH si value no coincide con value_type" $ do
      codeOf (parse "{\"expr\":{\"type\":\"Literal\",\"value\":\"700\",\"value_type\":\"Int\"}}")
        `shouldBe` Left "LITERAL_TYPE_MISMATCH"
      codeOf (parse "{\"expr\":{\"type\":\"Literal\",\"value\":1,\"value_type\":\"Bool\"}}")
        `shouldBe` Left "LITERAL_TYPE_MISMATCH"

    it "el mensaje de error incluye la ruta del nodo" $
      case parse "{\"expr\":{\"type\":\"BinaryOp\",\"op\":\">\",\"left\":\"credit_score\",\"right\":{\"type\":\"Var\",\"name\":\"a\"}}}" of
        Left (InvalidAst msg) -> msg `shouldContain` "$.expr.left"
        other -> expectationFailure ("se esperaba InvalidAst, se obtuvo " ++ show other)

  describe "envFromJSON" $ do
    it "deduce el tipo de cada variable desde su valor" $
      fmap (map (fmap literalType)) (envFromJSON =<< decodeValue "{\"a\":1,\"b\":true,\"c\":\"x\"}")
        `shouldBe` Right [("a", TInt), ("b", TBool), ("c", TString)]

    it "rechaza valores y nombres que no se pueden tipar" $ do
      (envFromJSON =<< decodeValue "{\"a\":1.5}") `shouldBe` Left (InvalidEnvValue "a")
      (envFromJSON =<< decodeValue "{\"a\":null}") `shouldBe` Left (InvalidEnvValue "a")
      (envFromJSON =<< decodeValue "{\"a\":[1]}") `shouldBe` Left (InvalidEnvValue "a")
      (envFromJSON =<< decodeValue "{\"A\":1}") `shouldBe` Left (InvalidEnvName "A")
      (envFromJSON =<< decodeValue "[1]") `shouldBe` Left EnvNotObject
  where
    decodeValue :: String -> Either EnvError Value
    decodeValue = either (const (Left EnvNotObject)) Right . eitherDecode . utf8

-- * Typechecker

typeCheckSpec :: Spec
typeCheckSpec = describe "Engine.TypeCheck" $ do
  describe "scope" $ do
    it "acepta variables de Γ y ligadas por Lam" $
      checkCode (App (Lam "s" TInt (BinaryOp Gt (Var "s") (Var "credit_score"))) (int 1))
        `shouldBe` Right TBool
    it "UNBOUND_VARIABLE con la primera variable libre ausente de Γ" $
      checkProgram gamma (Program (BinaryOp And (Var "risk") (Var "other")))
        `shouldBe` Left (UnboundVariable "risk")
    it "una variable ligada en un Lam no escapa de su cuerpo" $
      checkCode (App (Lam "s" TInt (Var "s")) (Var "s")) `shouldBe` Left "UNBOUND_VARIABLE"
    it "el alcance se verifica antes que los tipos" $
      checkCode (BinaryOp Gt (bool True) (Var "nope")) `shouldBe` Left "UNBOUND_VARIABLE"

  describe "operadores" $ do
    it "comparaciones: Int × Int → Bool" $ do
      checkCode (BinaryOp Lte (Var "credit_score") (int 700)) `shouldBe` Right TBool
      checkCode (BinaryOp Gt (Var "credit_score") (str "High")) `shouldBe` Left "OPERAND_MISMATCH"
      checkCode (BinaryOp Lt (str "a") (str "b")) `shouldBe` Left "OPERAND_MISMATCH"
    it "==: mismo tipo base a ambos lados" $ do
      checkCode (BinaryOp Eq (Var "customer_tier") (str "Gold")) `shouldBe` Right TBool
      checkCode (BinaryOp Eq (Var "has_defaults") (bool False)) `shouldBe` Right TBool
      checkCode (BinaryOp Eq (int 1) (bool True)) `shouldBe` Left "OPERAND_MISMATCH"
      checkCode (BinaryOp Eq (Lam "x" TInt (Var "x")) (Lam "x" TInt (Var "x")))
        `shouldBe` Left "OPERAND_MISMATCH"
    it "AND / OR: Bool × Bool → Bool" $ do
      checkCode (BinaryOp Or (Var "has_defaults") (bool True)) `shouldBe` Right TBool
      checkCode (BinaryOp And (Var "has_defaults") (int 1)) `shouldBe` Left "OPERAND_MISMATCH"

  describe "IfThenElse" $ do
    it "acepta condición Bool y ramas del mismo tipo" $
      checkCode (IfThenElse (Var "has_defaults") (int 100) (int 500)) `shouldBe` Right TInt
    it "CONDITION_NOT_BOOL" $
      checkCode (IfThenElse (Var "credit_score") (int 1) (int 2)) `shouldBe` Left "CONDITION_NOT_BOOL"
    it "BRANCH_MISMATCH" $
      checkProgram gamma (Program (IfThenElse (bool True) (int 500) (str "Rejected")))
        `shouldBe` Left (BranchMismatch TInt TString)

  describe "Lam / App" $ do
    let notB = Lam "b" TBool (IfThenElse (Var "b") (bool False) (bool True))
        twice = Lam "f" (TArrow TBool TBool) (Lam "x" TBool (App (Var "f") (App (Var "f") (Var "x"))))
    it "funciones de orden superior dentro del DSL" $
      checkCode (App (App twice notB) (Var "has_defaults")) `shouldBe` Right TBool
    it "el parámetro oculta a una variable de Γ con el mismo nombre" $
      checkCode (App (Lam "credit_score" TBool (Var "credit_score")) (bool True)) `shouldBe` Right TBool
    it "NOT_A_FUNCTION" $
      checkCode (App (Var "credit_score") (int 1)) `shouldBe` Left "NOT_A_FUNCTION"
    it "ARGUMENT_MISMATCH" $
      checkProgram gamma (Program (App notB (int 1))) `shouldBe` Left (ArgumentMismatch TBool TInt)
    it "NON_BASE_RESULT si el programa entero es una función" $
      checkCode notB `shouldBe` Left "NON_BASE_RESULT"

  it "el tipo de un literal es el de su valor" $
    property $ \(n :: Int) b s ->
      map (typeOf emptyEnv) [int n, bool b, str s] === map Right [TInt, TBool, TString]

-- * Fixtures compartidas (contracts/fixtures/)

data Fixture = Fixture
  { fxEnv :: Value
  , fxRaw :: String
  , fxStage :: String
  , fxOutcome :: String
  , fxExpect :: Either String String -- ^ código de error o tipo del resultado
  }

fixtureParser :: Value -> Parser Fixture
fixtureParser = withObject "Fixture" $ \o -> do
  ev <- o .: "expected_verdict"
  outcome <- ev .: "outcome"
  expect <-
    if outcome == "executed"
      then Right <$> ((ev .: "result") >>= (.: "type"))
      else Left <$> ev .: "error_code"
  Fixture <$> o .: "env" <*> o .: "llm_raw" <*> ev .: "stage" <*> pure outcome <*> pure expect

-- | Etapas estáticas del contrato: parse → scope → typecheck. Devuelve
-- @(etapa, Left código | Right tipo)@ para comparar con el veredicto esperado.
staticVerdict :: Fixture -> (String, Either String String)
staticVerdict fx = case envFromJSON (fxEnv fx) of
  Left err -> ("usage", Left (envErrorMessage err))
  Right env -> case parseProgram (utf8 (fxRaw fx)) of
    Left err -> ("parse", Left (parseErrorCode err))
    Right prog -> case checkProgram (map (fmap literalType) env) prog of
      Left err -> (stageName (errorStage err), Left (errorCode err))
      Right t -> ("execution", Right (renderType t))
  where
    stageName Scope = "scope"
    stageName TypeCheck = "typecheck"

fixturesSpec :: Spec
fixturesSpec = describe "contracts/fixtures" $
  mapM_ fixtureCase ["rule-00" ++ show n ++ ".json" | n <- [1 .. 7 :: Int]]
  where
    fixtureCase name = it name $ do
      bytes <- BL.readFile ("../contracts/fixtures/" ++ name)
      fx <- either fail pure (eitherDecode bytes >>= parseEither fixtureParser)
      staticVerdict fx `shouldBe` (fxStage fx, fxExpect fx)
      -- Los casos 'executed' todavía no se evalúan: solo se exige que pasen
      -- la verificación estática con el tipo del resultado esperado.
      fxOutcome fx `shouldSatisfy` (`elem` ["executed", "blocked"])
