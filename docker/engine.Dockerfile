# Imagen de desarrollo/test para engine/ (C-1, Haskell STLC).
FROM haskell:9.6-slim

WORKDIR /workspace/engine

# Cachear dependencias antes de copiar el código, para rebuilds rápidos.
COPY engine/engine.cabal ./
RUN cabal update && cabal build --only-dependencies --enable-tests

COPY engine/ ./
RUN cabal build --enable-tests

CMD ["cabal", "test"]
