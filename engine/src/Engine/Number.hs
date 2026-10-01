-- | Números del DSL (@contracts/README.md@ §1 y §3): límites de 'Int' y
-- 'Decimal', lectura exacta de números JSON y texto canónico de un 'Decimal'.
-- Sin punto flotante en ningún paso.
module Engine.Number
  ( intInRange
  , decimalInRange
  , isIntegral
  , scientificInt
  , scientificDecimal
  , renderDecimal
  ) where

import Data.Ratio (denominator, numerator, (%))
import Data.Scientific (Scientific, base10Exponent, coefficient, normalize)

-- Este módulo hace tres cosas con los números del DSL:
--   1. Controla los límites: Int de 64 bits y Decimal de hasta 28 dígitos
--      (intInRange, decimalInRange).
--   2. Lee los números del JSON en forma exacta (isIntegral, scientificInt,
--      scientificDecimal).
--   3. Escribe un Decimal como texto (renderDecimal).
-- Alternativa descartada: usar Double (punto flotante) para los decimales.
-- Es más simple, pero aproxima: con Double, 0.1 + 0.2 da 0.30000000000000004.
-- En reglas de negocio con montos eso no es aceptable; por eso se usa
-- Rational (fracción exacta): 0.1 se guarda como 1/10.
-- | 10^28: tope de valor absoluto y de denominador de un 'Decimal'.
decimalLimit :: Integer
decimalLimit = 10 ^ (28 :: Int)

-- | Entero de 64 bits con signo.
intInRange :: Integer -> Bool
intInRange n = n >= toInteger (minBound :: Int) && n <= toInteger (maxBound :: Int)

-- | Valor absoluto menor a 10^28 y denominador (reducido) de a lo sumo 10^28.
decimalInRange :: Rational -> Bool
decimalInRange q =
  abs (numerator q) < decimalLimit * denominator q && denominator q <= decimalLimit

-- | Un número JSON es entero si su valor lo es: @5000.0@ también.
isIntegral :: Scientific -> Bool
isIntegral s = base10Exponent (normalize s) >= 0

-- FP[Funciones totales]
-- | El número como 'Int', si es entero y entra en 64 bits. El exponente se
-- acota antes de calcular @10^e@, así un @1e1000000@ no agota la memoria.
scientificInt :: Scientific -> Maybe Int
scientificInt s
  | e < 0 || e > 19 = Nothing
  | intInRange n = Just (fromInteger n)
  | otherwise = Nothing
  where
    s' = normalize s
    e = base10Exponent s'
    n = coefficient s' * 10 ^ e

-- | El número como racional exacto, si tiene a lo sumo 28 decimales y valor
-- absoluto menor a 10^28. Los límites se miran sobre dígitos y exponente
-- antes de construir el racional.
scientificDecimal :: Scientific -> Maybe Rational
scientificDecimal s
  | e < -28 || digits + e > 28 = Nothing
  | decimalInRange q = Just q
  | otherwise = Nothing
  where
    s' = normalize s
    c = coefficient s'
    e = base10Exponent s'
    digits = if c == 0 then 0 else length (show (abs c))
    q = if e >= 0 then fromInteger (c * 10 ^ e) else c % (10 ^ negate e)

-- FP[Funciones puras] FP[Condicionales]
-- | Texto canónico (§3): posicional, sin exponente, sin ceros finales ni punto
-- final. Exacto si el valor termina en decimal; si no, 28 dígitos
-- significativos con redondeo half-even ('round' de Haskell redondea al par).
renderDecimal :: Rational -> String
renderDecimal q
  | q == 0 = "0"
  | otherwise = sign ++ place scaled places
  where
    sign = if q < 0 then "-" else ""
    a = abs q
    (scaled, places) = case terminatingPlaces (denominator a) of
      Just k -> (numerator (a * 10 ^ k), k)
      Nothing ->
        let k = 27 - magnitude a
         in (round (a * 10 ^^ k), k)

-- | Si @d@ solo tiene factores 2 y 5, los decimales que hacen falta.
terminatingPlaces :: Integer -> Maybe Int
terminatingPlaces d = if rest == 1 then Just (max twos fives) else Nothing
  where
    (twos, afterTwos) = strip 2 d
    (fives, rest) = strip 5 afterTwos
    strip p n = go 0 n
      where
        go k m
          | m `mod` p == 0 = go (k + 1) (m `div` p)
          | otherwise = (k, m)

-- | @e@ tal que @10^e <= a < 10^(e+1)@, para @a > 0@.
magnitude :: Rational -> Int
magnitude a
  | a >= 1 = length (show (floor a :: Integer)) - 1
  | otherwise = negate (until (\m -> a * 10 ^ m >= 1) (+ 1) 1)

-- | Escribe @n / 10^k@ con punto decimal y sin ceros finales.
place :: Integer -> Int -> String
place n k = trim (intPart ++ "." ++ fracPart)
  where
    ds = show n
    padded = replicate (k + 1 - length ds) '0' ++ ds
    (intPart, fracPart) = splitAt (length padded - k) padded
    trim = reverse . dropWhile (== '.') . dropWhile (== '0') . reverse
