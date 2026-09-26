-- | Entornos inmutables: el mismo tipo sirve para Γ (tipos) y, más adelante,
-- para los valores del evaluador.
module Engine.Env
  ( Env
  , emptyEnv
  , extend
  , lookupVar
  , names
  ) where

import Engine.Types (Name)

-- | Asociación nombre → dato. El binding más reciente queda al frente.
type Env a = [(Name, a)]

emptyEnv :: Env a
emptyEnv = []

-- | Devuelve un entorno nuevo; el original no cambia. Un nombre repetido
-- oculta al anterior.
extend :: Name -> a -> Env a -> Env a
extend x v env = (x, v) : env

lookupVar :: Name -> Env a -> Maybe a
lookupVar _ [] = Nothing
lookupVar x ((k, v) : rest)
  | x == k = Just v
  | otherwise = lookupVar x rest

names :: Env a -> [Name]
names = map fst
