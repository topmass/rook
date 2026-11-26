# Sources

Nova's shaders are written for Rook. No third-party code is copied into them.

- **pixelfx** (https://github.com/patch-gg/pixelfx), MIT License, Copyright (c) 2026 patch-gg. Its black-hole effect
  (itself adapted from Hugo Duprez's Sprite Fusion VFX, MIT) gave craft ideas for `icons/vortex.glsl`: inner rings
  hotter and faster, a gulp twice a loop, and debris that stretches into streaks as it falls. Its 12 fps steps
  confirmed Nova's choice to play on twos. Ideas only; no code taken.
- The hash in `../forge/prelude.glsl` follows the pcg3d idea of Jarzynski and Olano, "Hash Functions for GPU
  Rendering" (JCGT, 2020). It is written from scratch.
