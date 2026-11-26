(window.FORGE_PACKS ||= {})["nova"] = {
 "name": "nova",
 "title": "Nova",
 "format": 1,
 "kind": "flipbook",
 "cell": 256,
 "defaults": {
  "frames": 24,
  "fps": 12,
  "format": "webp",
  "quality": 0.7
 },
 "palette": {
  "ink": "#150B33",
  "deep": "#4B1FB8",
  "violet": "#8A45FF",
  "pink": "#FF5BD8",
  "core": "#FFF4FF",
  "cyan": "#46E6FF",
  "amber": "#FFB547",
  "rose": "#FF3D6A"
 },
 "icons": {
  "rest": {
   "src": "icons/rest.glsl",
   "frames": 36,
   "image": "baked/rest.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    6,
    6
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1094,
    0.3125,
    0.8906,
    0.6875
   ],
   "loop": true,
   "alpha": "straight"
  },
  "listen": {
   "src": "icons/listen.glsl",
   "layers": [
    "main",
    "voice"
   ],
   "voice": {
    "voice": {
     "opacity": [
      0.12,
      1.0
     ],
     "scale": [
      0.9,
      1.14
     ]
    }
   },
   "image": "baked/listen.webp",
   "frames": 24,
   "fps": 12,
   "cell": 256,
   "grid": [
    7,
    7
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1289,
    0.1289,
    0.8711,
    0.8711
   ],
   "loop": true,
   "alpha": "straight"
  },
  "helix": {
   "src": "icons/helix.glsl",
   "layers": [
    "main",
    "voice"
   ],
   "voice": {
    "voice": {
     "opacity": [
      0.45,
      1.0
     ],
     "scale": [
      1.0,
      1.04
     ],
     "stretch": [
      0.3,
      1.15
     ]
    }
   },
   "image": "baked/helix.webp",
   "frames": 24,
   "fps": 12,
   "cell": 256,
   "grid": [
    7,
    7
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.0781,
    0.2539,
    0.9219,
    0.7461
   ],
   "loop": true,
   "alpha": "straight"
  },
  "transcribe": {
   "src": "icons/rows.glsl",
   "frames": 36,
   "image": "baked/transcribe.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    6,
    6
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1172,
    0.2539,
    0.9141,
    0.7148
   ],
   "loop": true,
   "alpha": "straight"
  },
  "quill": {
   "src": "icons/quill.glsl",
   "frames": 24,
   "image": "baked/quill.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    5
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1289,
    0.1484,
    0.8828,
    0.793
   ],
   "loop": true,
   "alpha": "straight"
  },
  "rook": {
   "src": "icons/rook.glsl",
   "frames": 60,
   "think": true,
   "image": "baked/rook.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    8,
    8
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1016,
    0.0742,
    0.8984,
    0.9297
   ],
   "loop": true,
   "alpha": "straight"
  },
  "lattice": {
   "src": "icons/lattice.glsl",
   "think": true,
   "image": "baked/lattice.webp",
   "frames": 24,
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    5
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1797,
    0.1523,
    0.8203,
    0.8477
   ],
   "loop": true,
   "alpha": "straight"
  },
  "star": {
   "src": "icons/star.glsl",
   "think": true,
   "frames": 36,
   "image": "baked/star.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    6,
    6
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.0742,
    0.0742,
    0.9258,
    0.9258
   ],
   "loop": true,
   "alpha": "straight"
  },
  "synapse": {
   "src": "icons/synapse.glsl",
   "think": true,
   "frames": 36,
   "image": "baked/synapse.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    6,
    6
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1172,
    0.1133,
    0.8828,
    0.8164
   ],
   "loop": true,
   "alpha": "straight"
  },
  "board": {
   "src": "icons/board.glsl",
   "frames": 48,
   "think": true,
   "image": "baked/board.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    7,
    7
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1523,
    0.1992,
    0.8477,
    0.8516
   ],
   "loop": true,
   "alpha": "straight"
  },
  "speak": {
   "src": "icons/speak.glsl",
   "frames": 24,
   "layers": [
    "main",
    "glow",
    "wave"
   ],
   "voice": {
    "main": {
     "opacity": [
      1.0,
      1.0
     ],
     "scale": [
      0.96,
      1.05
     ]
    },
    "glow": {
     "opacity": [
      0.0,
      1.0
     ],
     "scale": [
      0.96,
      1.05
     ]
    },
    "wave": {
     "opacity": [
      0.55,
      1.0
     ],
     "scale": [
      0.96,
      1.05
     ],
     "stretch": [
      0.1,
      1.0
     ]
    }
   },
   "image": "baked/speak.webp",
   "fps": 12,
   "cell": 256,
   "grid": [
    9,
    8
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1055,
    0.1563,
    0.8945,
    0.9063
   ],
   "loop": true,
   "alpha": "straight"
  },
  "search": {
   "src": "icons/globe.glsl",
   "frames": 24,
   "image": "baked/search.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    5
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1836,
    0.2031,
    0.8164,
    0.7969
   ],
   "loop": true,
   "alpha": "straight"
  },
  "find": {
   "src": "icons/find.glsl",
   "frames": 24,
   "image": "baked/find.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    5
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1523,
    0.1172,
    0.8477,
    0.9023
   ],
   "loop": true,
   "alpha": "straight"
  },
  "cascade": {
   "src": "icons/cascade.glsl",
   "label": {
    "at": [
     0.5,
     0.93
    ],
    "size": 0.085
   },
   "image": "baked/cascade.webp",
   "frames": 24,
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    5
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.0938,
    0.0781,
    0.9063,
    0.8555
   ],
   "loop": true,
   "alpha": "straight"
  },
  "dispatch": {
   "src": "icons/dispatch.glsl",
   "frames": 36,
   "fps": 12,
   "layers": [
    "main",
    "tip_r",
    "tip_l"
   ],
   "tips": {
    "tip_r": {
     "at": [
      0.83,
      0.5
     ],
     "side": 1
    },
    "tip_l": {
     "at": [
      0.17,
      0.5
     ],
     "side": -1
    }
   },
   "intro": {
    "icon": "dispatch_in",
    "from": "rest"
   },
   "image": "baked/dispatch.webp",
   "cell": 256,
   "grid": [
    11,
    10
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.082,
    0.3086,
    0.918,
    0.6914
   ],
   "loop": true,
   "alpha": "straight"
  },
  "dispatch_in": {
   "src": "icons/dispatch_in.glsl",
   "frames": 18,
   "fps": 60,
   "loop": false,
   "image": "baked/dispatch_in.webp",
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    4
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.125,
    0.3086,
    0.875,
    0.6875
   ],
   "alpha": "straight"
  },
  "strand_head": {
   "src": "icons/strand_head.glsl",
   "cell": 64,
   "frames": 12,
   "fps": 24,
   "sprite": true,
   "image": "baked/strand_head.webp",
   "layers": [
    "main"
   ],
   "grid": [
    4,
    3
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.0938,
    0.2188,
    0.9375,
    0.7813
   ],
   "loop": true,
   "alpha": "straight"
  },
  "vortex": {
   "src": "icons/vortex.glsl",
   "image": "baked/vortex.webp",
   "frames": 24,
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    5
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1172,
    0.25,
    0.875,
    0.75
   ],
   "loop": true,
   "alpha": "straight"
  },
  "timer": {
   "src": "icons/hourglass.glsl",
   "frames": 48,
   "image": "baked/timer.webp",
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    7,
    7
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1406,
    0.1367,
    0.8594,
    0.8633
   ],
   "loop": true,
   "alpha": "straight"
  },
  "card": {
   "src": "icons/card.glsl",
   "image": "baked/card.webp",
   "frames": 24,
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    5
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.2266,
    0.1445,
    0.7734,
    0.8555
   ],
   "loop": true,
   "alpha": "straight"
  },
  "error": {
   "src": "icons/error.glsl",
   "image": "baked/error.webp",
   "frames": 24,
   "fps": 12,
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    5
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1289,
    0.1484,
    0.8516,
    0.8516
   ],
   "loop": true,
   "alpha": "straight"
  },
  "flash": {
   "src": "icons/flash.glsl",
   "frames": 20,
   "fps": 60,
   "loop": false,
   "image": "baked/flash.webp",
   "layers": [
    "main"
   ],
   "cell": 256,
   "grid": [
    5,
    4
   ],
   "pivot": [
    0.5,
    0.5
   ],
   "bbox": [
    0.1328,
    0.0977,
    0.875,
    0.8711
   ],
   "alpha": "straight"
  }
 },
 "states": {
  "rest": "rest",
  "listening": {
   "cycle": [
    "listen",
    "helix"
   ],
   "level": "in"
  },
  "transcribing": "transcribe",
  "thinking": {
   "rook": "rook",
   "turn": 3.0
  },
  "speaking": {
   "icon": "speak",
   "level": "out"
  },
  "send": "dispatch",
  "open": "vortex",
  "timer": "timer",
  "waiting": "card",
  "error": "error",
  "search": "search",
  "find": "find",
  "write": "quill"
 },
 "transition": {
  "seconds": 0.45,
  "from_scale": 0.88,
  "to_scale": 0.9,
  "flash": "flash",
  "flash_at": 0.08,
  "flash_scale": 0.8
 }
};
