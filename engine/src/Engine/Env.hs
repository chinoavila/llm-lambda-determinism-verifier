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

-- FP[Polimorfismo] FP[Tuplas]
-- | Asociación nombre → dato. El binding más reciente queda al frente.
type Env a = [(Name, a)]

-- | Entorno sin bindings; base para Γ y para el entorno de evaluación.
emptyEnv :: Env a
emptyEnv = []

-- FP[Inmutabilidad] FP[Funciones de listas]
-- | Devuelve un entorno nuevo; el original no cambia. Un nombre repetido
-- oculta al anterior.
extend :: Name -> a -> Env a -> Env a
extend x v env = (x, v) : env

-- FP[Patrones de listas] FP[Tuplas] FP[Recursión] FP[Guardas] FP[Reducciones] FP[Funciones totales]
-- | Busca desde el binding más reciente; devuelve 'Nothing' si el nombre falta.
lookupVar :: Name -> Env a -> Maybe a
lookupVar _ [] = Nothing
lookupVar x ((k, v) : rest)
  | x == k = Just v
  | otherwise = lookupVar x rest

-- FP[map/filter/fold]
-- | Proyecta los nombres en orden de precedencia (más reciente primero).
names :: Env a -> [Name]
names = map fst
