{-# LANGUAGE OverloadedStrings #-}

module Main (main) where

import Data.Aeson (Value, encode, eitherDecode, withObject, (.:))
import Data.Aeson.Types (Parser, parseEither)
import qualified Data.ByteString.Builder as B
import qualified Data.ByteString.Lazy as BL
import qualified Data.ByteString.Lazy.Char8 as BL8
import System.Exit (ExitCode (..))
import Test.Hspec
import Test.QuickCheck

import Engine.Cli
import Engine.Env (Env, emptyEnv, extend, lookupVar)
import Engine.Eval (EvalError (..), eval, evalProgram)
import qualified Engine.Eval as Eval
import Engine.Json
import Engine.Number (renderDecimal)
import Engine.TypeCheck
import Engine.Types

main :: IO ()
main = hspec $ do
  envSpec
  jsonSpec
  typeCheckSpec
  evalSpec
  cliSpec
  fixturesSpec

-- * Helpers

utf8 :: String -> BL.ByteString
utf8 = B.toLazyByteString . B.stringUtf8

parse :: String -> Either ParseError Program
parse = parseProgram . utf8

-- FP[Composición]
int :: Int -> Expr
int = Literal . VInt

bool :: Bool -> Expr
bool = Literal . VBool

str :: String -> Expr
str = Literal . VString

dec :: Rational -> Expr
dec = Literal . VDecimal

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

  -- FP[Funciones puras]
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

    it "acepta todos los operadores binarios" $
      let src op = "{\"expr\":{\"type\":\"BinaryOp\",\"op\":\"" ++ opSymbol op ++ "\",\
                   \\"left\":{\"type\":\"Var\",\"name\":\"a\"},\"right\":{\"type\":\"Var\",\"name\":\"b\"}}}"
       in [parse (src op) | op <- [minBound .. maxBound]]
            `shouldBe` [Right (Program (BinaryOp op (Var "a") (Var "b"))) | op <- [minBound .. maxBound]]

    it "MALFORMED_JSON si no es JSON" $ do
      codeOf (parse "{\"expr\":") `shouldBe` Left "MALFORMED_JSON"
      codeOf (parse "") `shouldBe` Left "MALFORMED_JSON"

    -- FP[Funciones anónimas]
    it "INVALID_AST ante formas que el contrato no permite" $
      mapM_
        (\src -> codeOf (parse src) `shouldBe` Left "INVALID_AST")
        [ "{\"type\":\"Var\",\"name\":\"x\"}" -- falta la raíz expr
        , "{\"expr\":{\"type\":\"Var\",\"name\":\"x\"},\"extra\":1}" -- clave extra en la raíz
        , "{\"expr\":{\"type\":\"Var\",\"name\":\"x\",\"value_type\":\"Int\"}}" -- clave extra en un nodo
        , "{\"expr\":{\"type\":\"Let\",\"name\":\"x\"}}" -- constructor inexistente
        , "{\"expr\":{\"type\":\"BinaryOp\",\"op\":\"^\",\"left\":{\"type\":\"Var\",\"name\":\"a\"},\"right\":{\"type\":\"Var\",\"name\":\"b\"}}}"
        , "{\"expr\":{\"type\":\"UnaryOp\",\"op\":\"-\",\"operand\":{\"type\":\"Var\",\"name\":\"a\"}}}"
        , "{\"expr\":{\"type\":\"In\",\"value\":{\"type\":\"Var\",\"name\":\"a\"},\"options\":[]}}" -- options vacía
        , "{\"expr\":{\"type\":\"Var\"}}" -- campo faltante
        , "{\"expr\":{\"type\":\"Var\",\"name\":\"Credit\"}}" -- nombre fuera del patrón
        , "{\"expr\":{\"type\":\"Literal\",\"value\":1e30,\"value_type\":\"Int\"}}" -- fuera de 64 bits
        , "{\"expr\":{\"type\":\"Literal\",\"value\":1e28,\"value_type\":\"Decimal\"}}" -- fuera de 10^28
        , "{\"expr\":{\"type\":\"Literal\",\"value\":1e-29,\"value_type\":\"Decimal\"}}" -- más de 28 decimales
        , "{\"expr\":{\"type\":\"Literal\",\"value\":1e999999999,\"value_type\":\"Decimal\"}}" -- sin agotar memoria
        , "{\"expr\":{\"type\":\"Literal\",\"value\":null,\"value_type\":\"Int\"}}"
        , "{\"expr\":{\"type\":\"Literal\",\"value\":1,\"value_type\":\"Float\"}}"
        , "{\"expr\":{\"type\":\"Lam\",\"param\":\"x\",\"param_type\":{\"from\":\"Int\"},\"body\":{\"type\":\"Var\",\"name\":\"x\"}}}"
        ]

    it "LITERAL_TYPE_MISMATCH si value no coincide con value_type" $ do
      codeOf (parse "{\"expr\":{\"type\":\"Literal\",\"value\":\"700\",\"value_type\":\"Int\"}}")
        `shouldBe` Left "LITERAL_TYPE_MISMATCH"
      codeOf (parse "{\"expr\":{\"type\":\"Literal\",\"value\":1,\"value_type\":\"Bool\"}}")
        `shouldBe` Left "LITERAL_TYPE_MISMATCH"
      codeOf (parse "{\"expr\":{\"type\":\"Literal\",\"value\":7.5,\"value_type\":\"Int\"}}")
        `shouldBe` Left "LITERAL_TYPE_MISMATCH"
      codeOf (parse "{\"expr\":{\"type\":\"Literal\",\"value\":\"0.3\",\"value_type\":\"Decimal\"}}")
        `shouldBe` Left "LITERAL_TYPE_MISMATCH"

    it "literales Decimal exactos; un entero también sirve como Decimal" $ do
      parse "{\"expr\":{\"type\":\"Literal\",\"value\":0.30,\"value_type\":\"Decimal\"}}"
        `shouldBe` Right (Program (dec (3 / 10)))
      parse "{\"expr\":{\"type\":\"Literal\",\"value\":5000,\"value_type\":\"Decimal\"}}"
        `shouldBe` Right (Program (dec 5000))
      parse "{\"expr\":{\"type\":\"Literal\",\"value\":5000.0,\"value_type\":\"Int\"}}"
        `shouldBe` Right (Program (int 5000))
      parse "{\"expr\":{\"type\":\"Literal\",\"value\":1e-28,\"value_type\":\"Decimal\"}}"
        `shouldBe` Right (Program (dec (1 / 10 ^ (28 :: Int))))

    it "UnaryOp e In" $
      parse
        "{\"expr\":{\"type\":\"UnaryOp\",\"op\":\"NOT\",\"operand\":{\"type\":\"In\",\
        \\"value\":{\"type\":\"Var\",\"name\":\"t\"},\"options\":[{\"type\":\"Literal\",\
        \\"value\":\"Gold\",\"value_type\":\"String\"}]}}}"
        `shouldBe` Right (Program (UnaryOp Not (In (Var "t") [str "Gold"])))

    it "el mensaje de error incluye la ruta del nodo" $
      case parse "{\"expr\":{\"type\":\"BinaryOp\",\"op\":\">\",\"left\":\"credit_score\",\"right\":{\"type\":\"Var\",\"name\":\"a\"}}}" of
        Left (InvalidAst msg) -> msg `shouldContain` "$.expr.left"
        other -> expectationFailure ("se esperaba InvalidAst, se obtuvo " ++ show other)

  describe "envFromJSON" $ do
    it "deduce el tipo de cada variable desde su valor" $
      fmap (map (fmap literalType)) (envFromJSON =<< decodeValue "{\"a\":1,\"b\":true,\"c\":\"x\",\"d\":0.30,\"e\":5000.0}")
        `shouldBe` Right [("a", TInt), ("b", TBool), ("c", TString), ("d", TDecimal), ("e", TInt)]

    it "un decimal del env es exacto" $
      (envFromJSON =<< decodeValue "{\"d\":1250.75}") `shouldBe` Right [("d", VDecimal (125075 / 100))]

    it "rechaza valores y nombres que no se pueden tipar" $ do
      (envFromJSON =<< decodeValue "{\"a\":1e30}") `shouldBe` Left (InvalidEnvValue "a")
      (envFromJSON =<< decodeValue "{\"a\":1e-40}") `shouldBe` Left (InvalidEnvValue "a")
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

  describe "aritmética y Decimal" $ do
    it "+ - * entre Int dan Int; con un Decimal, Decimal (promoción en operadores)" $ do
      checkCode (BinaryOp Add (Var "credit_score") (int 1)) `shouldBe` Right TInt
      checkCode (BinaryOp Mul (Var "credit_score") (dec 0.3)) `shouldBe` Right TDecimal
      checkCode (BinaryOp Sub (dec 1) (Var "credit_score")) `shouldBe` Right TDecimal
    it "/ siempre da Decimal; % solo entre Int" $ do
      checkCode (BinaryOp Div (int 7) (int 2)) `shouldBe` Right TDecimal
      checkCode (BinaryOp Mod (int 7) (int 2)) `shouldBe` Right TInt
      checkCode (BinaryOp Mod (dec 7) (int 2)) `shouldBe` Left "OPERAND_MISMATCH"
    it "la aritmética no admite Bool ni String" $ do
      checkCode (BinaryOp Add (str "a") (str "b")) `shouldBe` Left "OPERAND_MISMATCH"
      checkCode (BinaryOp Mul (bool True) (int 2)) `shouldBe` Left "OPERAND_MISMATCH"
    it "comparaciones e igualdad entre Int y Decimal" $ do
      checkCode (BinaryOp Lte (Var "credit_score") (dec 700.5)) `shouldBe` Right TBool
      checkCode (BinaryOp Eq (int 1) (dec 1)) `shouldBe` Right TBool
      checkCode (BinaryOp Neq (Var "customer_tier") (str "Basic")) `shouldBe` Right TBool
      checkCode (BinaryOp Neq (int 1) (str "1")) `shouldBe` Left "OPERAND_MISMATCH"
    it "sin promoción en App: Int donde se espera Decimal es ARGUMENT_MISMATCH" $
      checkProgram gamma (Program (App (Lam "x" TDecimal (BinaryOp Gt (Var "x") (int 0))) (int 1)))
        `shouldBe` Left (ArgumentMismatch TDecimal TInt)

  describe "NOT e In" $ do
    it "NOT: Bool → Bool" $ do
      checkCode (UnaryOp Not (Var "has_defaults")) `shouldBe` Right TBool
      checkProgram gamma (Program (UnaryOp Not (int 1))) `shouldBe` Left (UnaryMismatch Not TInt)
    it "In: opciones del tipo del valor, con promoción numérica" $ do
      checkCode (In (Var "customer_tier") [str "Gold", str "Platinum"]) `shouldBe` Right TBool
      checkCode (In (Var "credit_score") [int 700, dec 750.5]) `shouldBe` Right TBool
      checkProgram gamma (Program (In (Var "customer_tier") [str "Gold", int 1]))
        `shouldBe` Left (InMismatch TString TInt)
    it "In revisa el alcance de value y de las opciones" $
      checkCode (In (Var "credit_score") [Var "nope"]) `shouldBe` Left "UNBOUND_VARIABLE"

  describe "IfThenElse" $ do
    it "acepta condición Bool y ramas del mismo tipo" $
      checkCode (IfThenElse (Var "has_defaults") (int 100) (int 500)) `shouldBe` Right TInt
    it "CONDITION_NOT_BOOL" $
      checkCode (IfThenElse (Var "credit_score") (int 1) (int 2)) `shouldBe` Left "CONDITION_NOT_BOOL"
    it "BRANCH_MISMATCH" $
      checkProgram gamma (Program (IfThenElse (bool True) (int 500) (str "Rejected")))
        `shouldBe` Left (BranchMismatch TInt TString)

  -- FP[Funciones lambda] FP[Orden superior]
  describe "Lam / App" $ do
    let notB = Lam "b" TBool (IfThenElse (Var "b") (bool False) (bool True))
        twice = Lam "f" (TArrow TBool TBool) (Lam "x" TBool (App (Var "f") (App (Var "f") (Var "x"))))
    it "funciones de orden superior dentro del DSL" $
      checkCode (App (App twice notB) (Var "has_defaults")) `shouldBe` Right TBool
    -- FP[Currificación]
    it "aplicación parcial en el DSL: twice notB : Bool → Bool" $ do
      typeOf gamma twice `shouldBe` Right (TArrow (TArrow TBool TBool) (TArrow TBool TBool))
      typeOf gamma (App twice notB) `shouldBe` Right (TArrow TBool TBool)
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

-- * Evaluador

evalSpec :: Spec
evalSpec = describe "Engine.Eval" $ do
  let caseEnv = [("credit_score", VInt 750), ("has_defaults", VBool False), ("customer_tier", VString "Gold")]
      run' = evalProgram caseEnv . Program

  it "un literal evalúa a sí mismo" $
    property $ \(n :: Int) b s ->
      map run' [int n, bool b, str s] === map Right [VInt n, VBool b, VString s]

  it "las comparaciones coinciden con las de Haskell" $
    property $ \(a :: Int) b ->
      map (\op -> run' (BinaryOp op (int a) (int b))) [Gt, Lt, Gte, Lte, Eq]
        === map (Right . VBool) [a > b, a < b, a >= b, a <= b, a == b]

  it "== sobre cadenas y booleanos; AND / OR" $ do
    run' (BinaryOp Eq (Var "customer_tier") (str "Gold")) `shouldBe` Right (VBool True)
    run' (BinaryOp Eq (Var "has_defaults") (bool True)) `shouldBe` Right (VBool False)
    run' (BinaryOp And (bool True) (Var "has_defaults")) `shouldBe` Right (VBool False)
    run' (BinaryOp Or (bool False) (bool True)) `shouldBe` Right (VBool True)

  describe "aritmética exacta" $ do
    it "0.1 + 0.2 == 0.3" $
      run' (BinaryOp Eq (BinaryOp Add (dec 0.1) (dec 0.2)) (dec 0.3)) `shouldBe` Right (VBool True)
    it "Int con Int queda Int; con Decimal, Decimal; / siempre Decimal" $ do
      run' (BinaryOp Mul (int 6) (int 7)) `shouldBe` Right (VInt 42)
      run' (BinaryOp Mul (Var "credit_score") (dec 0.3)) `shouldBe` Right (VDecimal 225)
      run' (BinaryOp Div (int 7) (int 2)) `shouldBe` Right (VDecimal 3.5)
    it "% con el signo del divisor, como Python" $ do
      run' (BinaryOp Mod (int (-7)) (int 3)) `shouldBe` Right (VInt 2)
      run' (BinaryOp Mod (int 7) (int (-3))) `shouldBe` Right (VInt (-2))
    it "1 == 1.0 y != " $ do
      run' (BinaryOp Eq (int 1) (dec 1)) `shouldBe` Right (VBool True)
      run' (BinaryOp Neq (Var "customer_tier") (str "Gold")) `shouldBe` Right (VBool False)
    it "las operaciones entre Int coinciden con las de Integer mientras no desborden" $
      property $ \(a :: Int) b ->
        let exact = toInteger a + toInteger b
         in run' (BinaryOp Add (int a) (int b))
              === if abs exact <= toInteger (maxBound :: Int) then Right (VInt (a + b)) else Left (Eval.Runtime Eval.NumericOverflow)

  describe "errores en ejecución (Runtime, no atascos)" $ do
    it "división por cero en / y %" $ do
      run' (BinaryOp Div (int 1) (int 0)) `shouldBe` Left (Eval.Runtime Eval.DivisionByZero)
      run' (BinaryOp Div (dec 1) (dec 0)) `shouldBe` Left (Eval.Runtime Eval.DivisionByZero)
      run' (BinaryOp Mod (int 1) (int 0)) `shouldBe` Left (Eval.Runtime Eval.DivisionByZero)
    it "desborde de Int y de Decimal" $ do
      run' (BinaryOp Add (int maxBound) (int 1)) `shouldBe` Left (Eval.Runtime Eval.NumericOverflow)
      run' (BinaryOp Mul (dec (10 ^ (27 :: Int))) (int 10)) `shouldBe` Left (Eval.Runtime Eval.NumericOverflow)
    it "AND / OR cortocircuitan: una guarda protege la división" $ do
      let guarded x = BinaryOp And (BinaryOp Neq x (int 0)) (BinaryOp Gt (BinaryOp Div (int 10) x) (int 2))
      run' (guarded (int 0)) `shouldBe` Right (VBool False)
      run' (guarded (int 4)) `shouldBe` Right (VBool True)
      run' (BinaryOp Or (bool True) (BinaryOp Gt (BinaryOp Div (int 1) (int 0)) (int 0))) `shouldBe` Right (VBool True)

  describe "NOT e In" $ do
    it "NOT niega" $ run' (UnaryOp Not (Var "has_defaults")) `shouldBe` Right (VBool True)
    it "In busca la primera opción igual y no evalúa las siguientes" $ do
      run' (In (Var "customer_tier") [str "Silver", str "Gold"]) `shouldBe` Right (VBool True)
      run' (In (Var "customer_tier") [str "Silver"]) `shouldBe` Right (VBool False)
      run' (In (int 750) [Var "credit_score", BinaryOp Div (int 1) (int 0)]) `shouldBe` Right (VBool True)
      run' (In (int 1) [dec 1]) `shouldBe` Right (VBool True)

  it "IfThenElse elige la rama según la condición" $ do
    run' (IfThenElse (BinaryOp Gt (Var "credit_score") (int 700)) (int 500) (int 0))
      `shouldBe` Right (VInt 500)
    run' (IfThenElse (Var "has_defaults") (str "no") (str "si")) `shouldBe` Right (VString "si")

  -- FP[Funciones lambda] FP[Orden superior]
  describe "Lam / App" $ do
    let notB = Lam "b" TBool (IfThenElse (Var "b") (bool False) (bool True))
        twice = Lam "f" (TArrow TBool TBool) (Lam "x" TBool (App (Var "f") (App (Var "f") (Var "x"))))
    it "β-reducción con llamada por valor" $
      run' (App (Lam "s" TInt (BinaryOp Gt (Var "s") (int 700))) (Var "credit_score"))
        `shouldBe` Right (VBool True)
    it "funciones de orden superior dentro del DSL" $ do
      run' (App notB (Var "has_defaults")) `shouldBe` Right (VBool True)
      run' (App (App twice notB) (Var "has_defaults")) `shouldBe` Right (VBool False)
    -- FP[Currificación]
    it "aplicación parcial: twice notB es una clausura que espera el segundo argumento" $
      fmap isClosure (eval [] (App twice notB)) `shouldBe` Right True
    it "el parámetro oculta a una variable del caso" $
      run' (App (Lam "credit_score" TBool (Var "credit_score")) (bool True)) `shouldBe` Right (VBool True)
    it "alcance léxico: una clausura usa el entorno donde se definió" $
      -- (λf. (λx. f true) 99) (λb. x), con x = 5 en el caso: da 5, no 99.
      evalProgram [("x", VInt 5)]
        ( Program
            ( App
                (Lam "f" (TArrow TBool TInt) (App (Lam "x" TInt (App (Var "f") (bool True))) (int 99)))
                (Lam "b" TBool (Var "x"))
            )
        )
        `shouldBe` Right (VInt 5)

  it "se atasca (sin excepciones) sobre programas mal tipados" $ do
    eval [] (App (int 1) (int 2)) `shouldBe` Left StuckApp
    eval [] (Var "x") `shouldBe` Left (StuckVar "x")
    eval [] (BinaryOp Gt (bool True) (int 1)) `shouldBe` Left (StuckOp Gt)
    eval [] (IfThenElse (int 1) (int 2) (int 3)) `shouldBe` Left StuckIf
    evalProgram [] (Program (Lam "x" TInt (Var "x"))) `shouldBe` Left StuckResult
    fmap isClosure (eval [] (Lam "x" TInt (Var "x"))) `shouldBe` Right True
  where
    isClosure (Eval.VClosure {}) = True
    isClosure _ = False

-- * CLI

cliSpec :: Spec
cliSpec = describe "Engine.Cli" $ do
  describe "encodeVerdict" $ do
    it "respeta el orden de claves de los ejemplos del contrato" $ do
      encodeVerdict (Executed (VBool True))
        `shouldBe` "{\"outcome\":\"executed\",\"stage\":\"execution\",\"result\":{\"type\":\"Bool\",\"value\":true},\"error\":null}\n"
      encodeVerdict (BlockedCheck (BranchMismatch TInt TString))
        `shouldBe` "{\"outcome\":\"blocked\",\"stage\":\"typecheck\",\"result\":null,\"error\":{\"code\":\"BRANCH_MISMATCH\",\"message\":\"then: Int, else: String\"}}\n"
    it "runtime_error y Decimal como texto canónico" $ do
      encodeVerdict (RuntimeFailure Eval.DivisionByZero)
        `shouldBe` utf8 "{\"outcome\":\"runtime_error\",\"stage\":\"execution\",\"result\":null,\"error\":{\"code\":\"DIVISION_BY_ZERO\",\"message\":\"división por cero\"}}\n"
      encodeVerdict (Executed (VDecimal 1500.5))
        `shouldBe` "{\"outcome\":\"executed\",\"stage\":\"execution\",\"result\":{\"type\":\"Decimal\",\"value\":\"1500.5\"},\"error\":null}\n"
    it "los códigos de salida siguen la etapa" $
      map verdictExit
        [ Executed (VInt 1)
        , BlockedParse (MalformedJson "")
        , BlockedCheck (UnboundVariable "x")
        , BlockedCheck (NotAFunction TInt)
        , RuntimeFailure Eval.NumericOverflow
        ]
        `shouldBe` [ExitSuccess, ExitFailure 1, ExitFailure 2, ExitFailure 3, ExitFailure 4]

  describe "renderDecimal" $ do
    it "exacto si termina, sin ceros finales ni exponente" $
      map renderDecimal [1500.5, 0.3, -2, 0, 12.50, 1 / 10 ^ (28 :: Int), 10 ^ (27 :: Int)]
        `shouldBe` ["1500.5", "0.3", "-2", "0", "12.5", "0." ++ replicate 27 '0' ++ "1", '1' : replicate 27 '0']
    it "si no termina, 28 dígitos significativos half-even (como decimal de Python)" $ do
      renderDecimal (10 / 3) `shouldBe` "3.333333333333333333333333333"
      renderDecimal (10000 / 12) `shouldBe` "833.3333333333333333333333333"
      renderDecimal (-2 / 3) `shouldBe` "-0.6666666666666666666666666667"
      renderDecimal (1 / 7) `shouldBe` "0.1428571428571428571428571429"

  describe "run" $ do
    it "sin --env, Γ es vacío" $
      run [] (utf8 "{\"expr\":{\"type\":\"Literal\",\"value\":\"ok\",\"value_type\":\"String\"}}")
        `shouldBe` Response ExitSuccess "{\"outcome\":\"executed\",\"stage\":\"execution\",\"result\":{\"type\":\"String\",\"value\":\"ok\"},\"error\":null}\n" ""

    -- FP[Evaluación perezosa]
    it "--print-gamma imprime Γ ordenado y no lee stdin" $
      run ["--env", "{\"has_defaults\":true,\"credit_score\":1,\"customer_tier\":\"x\"}", "--print-gamma"]
        (error "no se debe leer stdin")
        `shouldBe` Response ExitSuccess "{\"credit_score\":\"Int\",\"customer_tier\":\"String\",\"has_defaults\":\"Bool\"}\n" ""

    it "--print-gamma sin --env imprime {}" $
      resStdout (run ["--print-gamma"] "") `shouldBe` "{}\n"

    it "exit 64 con stdout vacío ante un error de uso" $
      mapM_
        ( \args -> do
            let r = run args "{\"expr\":{\"type\":\"Literal\",\"value\":1,\"value_type\":\"Int\"}}"
            (resExit r, resStdout r) `shouldBe` (ExitFailure 64, "")
            resStderr r `shouldNotBe` ""
        )
        [ ["--verbose"]
        , ["--env"]
        , ["--env", "{\"a\":"]
        , ["--env", "[1]"]
        , ["--env", "{\"a\":1e30}"]
        , ["--env", "{\"A\":1}"]
        , ["--env", "{}", "--env", "{}"]
        , ["--print-gamma", "--print-gamma"]
        ]

-- * Fixtures compartidas (contracts/fixtures/)

-- | (exit, outcome, stage, Left código de error | Right result)
type Summary = (Int, String, String, Either String Value)

-- FP[Condicionales]
expectedParser :: Value -> Parser Summary
expectedParser = withObject "expected_verdict" $ \ev -> do
  outcome <- ev .: "outcome"
  detail <-
    if outcome == "executed"
      then Right <$> ev .: "result"
      else Left <$> ev .: "error_code"
  (,,,) <$> ev .: "exit_code" <*> pure outcome <*> ev .: "stage" <*> pure detail

-- | Lo mismo, leído de la línea que el engine escribe en stdout.
actualSummary :: Response -> Either String Summary
actualSummary r = do
  v <- eitherDecode (resStdout r)
  flip parseEither v $ withObject "Verdict" $ \o -> do
    outcome <- o .: "outcome"
    detail <-
      if outcome == "executed"
        then Right <$> o .: "result"
        else Left <$> ((o .: "error") >>= (.: "code"))
    (,,,) (exitNumber (resExit r)) outcome <$> o .: "stage" <*> pure detail
  where
    exitNumber ExitSuccess = 0
    exitNumber (ExitFailure n) = n

-- FP[Listas por comprensión]
-- | Cada fixture pasa por la CLI completa, igual que la va a invocar el
-- orquestador: @engine --env '<env>' < llm_raw@.
fixturesSpec :: Spec
fixturesSpec = describe "contracts/fixtures" $
  mapM_ fixtureCase ["rule-" ++ pad (show n) ++ ".json" | n <- [1 .. 15 :: Int]]
  where
    pad s = replicate (3 - length s) '0' ++ s
    fixtureCase name = it name $ do
      bytes <- BL.readFile ("../contracts/fixtures/" ++ name)
      (env, raw, expected) <- either fail pure $ do
        v <- eitherDecode bytes
        flip parseEither v $ withObject "Fixture" $ \o ->
          (,,) <$> o .: "env" <*> o .: "llm_raw" <*> (o .: "expected_verdict" >>= expectedParser)
      -- Las fixtures son ASCII, así que Char8 alcanza para pasar el env como argumento.
      let r = run ["--env", BL8.unpack (encode (env :: Value))] (utf8 raw)
      actualSummary r `shouldBe` Right expected
      BL8.count '\n' (resStdout r) `shouldBe` 1
      BL8.last (resStdout r) `shouldBe` '\n'
