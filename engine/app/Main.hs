-- | Punto de entrada IO del ejecutable del engine. Adapta argv y stdin a la
-- función pura 'Engine.Cli.run', y traduce su respuesta a stdout, stderr y
-- código de salida según el contrato de @contracts/README.md@ §2.
module Main (main) where

import Control.Exception (SomeException, displayException, evaluate, handle)
import Control.Monad (unless)
import qualified Data.ByteString as BS
import qualified Data.ByteString.Lazy as BL
import GHC.IO.Encoding (setFileSystemEncoding, utf8)
import System.Environment (getArgs)
import System.Exit (ExitCode (..), exitWith)
import System.IO (hPutStrLn, hSetEncoding, stderr)

import Engine.Cli (Response (..), run)

-- | IO alrededor de 'run' (contrato en @contracts/README.md@ §2). La salida
-- se calcula entera antes de escribir: si algo falla, stdout queda vacío y
-- se sale con 70, nunca con un código que el orquestador confunda con un
-- bloqueo.
main :: IO ()
main = do
  -- argv y stderr en UTF-8, sin depender del locale del contenedor.
  setFileSystemEncoding utf8
  hSetEncoding stderr utf8
  code <- handle internalError $ do
    args <- getArgs
    input <- BL.getContents
    let Response exit out err = run args input
    bytes <- evaluate (BL.toStrict out)
    unless (null err) (hPutStrLn stderr err)
    BS.putStr bytes
    pure exit
  exitWith code

internalError :: SomeException -> IO ExitCode
internalError e = do
  hPutStrLn stderr ("error interno: " ++ displayException e)
  pure (ExitFailure 70)
