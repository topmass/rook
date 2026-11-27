#!/bin/sh
# Install the files for Rook's medium voice on Linux with an NVIDIA graphics card. On a Mac, launchd/install-voice.sh does it: Qwen3-TTS 0.6B on qwentts.cpp
# with CUDA (desktop/medium_voice.py), in $XDG_DATA_HOME/rook/medium-voice.
# About 3.3 GB on disk (1.1 GB environment, 2.2 GB model). The model loads only while Rook uses the medium voice.
# install/install.sh --voice medium runs this, then records the files, writes the user unit and points Rook at it.
# Usage: install/medium-voice.sh           install the environment and the model.
#        install/medium-voice.sh --check   exits 0 when this computer can run it, else says why and exits 1.
# ROOK_MEDIUM_MIN_VRAM_GB (default 6) is the least graphics memory, in GB, that gets the medium voice.
set -eu

here=$(cd "$(dirname "$0")/.." && pwd)
[ "$(uname -s)" != Darwin ] || exec sh "$here/launchd/install-voice.sh" "$@"
data="${XDG_DATA_HOME:-$HOME/.local/share}/rook/medium-voice"
min_gb="${ROOK_MEDIUM_MIN_VRAM_GB:-6}"

# The CUDA 12.8 build runs on NVIDIA cards from the RTX 20 series on (compute 7.5) with driver 570 or newer.
why_not() {
	gpu=$(nvidia-smi --query-gpu=compute_cap,memory.total,driver_version --format=csv,noheader,nounits 2>/dev/null | head -n 1) || gpu=""
	case "$gpu" in
		[0-9]*.[0-9]*,\ [0-9]*,\ [0-9]*) ;;
		*)
			echo "This computer keeps the small voice, because the medium voice needs an NVIDIA graphics card and its driver."
			return ;;
	esac
	IFS=', ' read -r cap mib driver <<EOF
$gpu
EOF
	major=${cap%%.*}
	minor=${cap#*.}
	if [ "$major" -lt 7 ] || { [ "$major" -eq 7 ] && [ "$minor" -lt 5 ]; }; then
		echo "This computer keeps the small voice, because the medium voice needs an NVIDIA RTX 20 series card or newer."
	elif [ "${driver%%.*}" -lt 570 ]; then
		echo "This computer keeps the small voice, because the medium voice needs NVIDIA driver 570 or newer, and this one is $driver."
	elif [ "$((mib / 1000))" -lt "$min_gb" ]; then
		echo "This computer keeps the small voice, because the medium voice needs $min_gb GB of graphics memory, and this card has $((mib / 1000)) GB."
	fi
}

reason=$(why_not)
if [ "${1:-}" = "--check" ]; then
	[ -z "$reason" ] && exit 0
	echo "$reason"
	exit 1
fi
[ -z "$reason" ] || { echo "$reason" >&2; exit 1; }
uv=$(command -v uv || echo "$HOME/.local/bin/uv")
[ -x "$uv" ] || { echo "The medium voice needs uv. Install it with: sudo pacman -S --needed uv" >&2; exit 1; }

echo "  Installing the medium voice in $data (about 3.3 GB)..."
mkdir -p "$data"
[ -x "$data/venv/bin/python" ] || "$uv" venv -q --python 3.12 "$data/venv"
"$uv" pip install -q --python "$data/venv/bin/python" qwentts-cpp-python==0.5.0 \
	nvidia-cuda-runtime-cu12==12.8.90 nvidia-cublas-cu12==12.8.4.1
echo "  Downloading the medium voice's model, about 2.2 GB. It shows no progress, so the log stays quiet until it ends."
HF_HUB_DISABLE_PROGRESS_BARS=1 "$data/venv/bin/python" "$here/desktop/medium_voice.py" --download >/dev/null
echo "  The medium voice's model is downloaded."
