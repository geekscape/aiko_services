#!/usr/bin/env bash
#
# Usage
# ~~~~~
#   export HYPERSPACE_IMPL=shell         # shell | python
#   export HYPERSPACE_RANDOM_HASH=false  # use incrementing hash value
#   source hyperspace.sh
#
#   _ln      new_link  node        # node | category
#   _ls      [-l] [-n] [-r] [path]
#   _mk      node                  # node only
#   _mkdir   category              # category only
#   _rm      node                  # node | category
#   _storage [-s]
#
# To Do
# ~~~~~
# - BUG: These commands only work in the top-level directory ...
#        - "_mk", "_mkdir", "_ls", "_ln", "_rm" and "_storage"
#
# - Review / improve code via ChatGPT, as per ...
#   - https://chatgpt.com/c/685cc9c2-29b4-8002-befb-0f00c872d1ad

if ! (return 0 2>/dev/null); then
  echo 'Error: Must use "source hyperspace.sh"' >&2
  exit 1
fi

if [[ "${HYPERSPACE_IMPL:-shell}" == "python" ]]; then
  _ln() {
    aiko_hyperspace ln "$1" "$2"
  }
  _ls() {
    aiko_hyperspace ls "$@"
  }
  _mk() {
    aiko_hyperspace mk "$1"
  }
  _mkdir() {
    aiko_hyperspace mkdir "$1"
  }
  _rm() {
    aiko_hyperspace rm "$1"
  }
  _storage() {
    aiko_hyperspace storage "$@"
  }
  return 0
fi

# set -euo pipefail  # TODO: _storage() causes shell to exit
IFS=$'\n\t'

ROOT_FILENAME=".root"
STORAGE_FILENAME="storage"
TRACK_PATHNAME="$STORAGE_FILENAME/tracked_paths"
HASH_LENGTH=12  # 6 bytes = 12 hex digits
HASH_PATHNAME="$STORAGE_FILENAME/hash_counter"

__initialize() {
  if [ ! -L "$ROOT_FILENAME" ]; then
    ln -s "$(pwd)" "$ROOT_FILENAME"
    echo "Created $ROOT_FILENAME --> $(pwd)"
  fi
  if [ ! -d "$STORAGE_FILENAME" ]; then
    mkdir -p "$STORAGE_FILENAME"
    echo "Created $STORAGE_FILENAME"
  fi
  if [ ! -f "$HASH_PATHNAME" ]; then
    echo 0 >"$HASH_PATHNAME"
  fi
  HASH_COUNTER=$(cat "$HASH_PATHNAME")
}

__generateHash() {
  if [[ "${HYPERSPACE_RANDOM_HASH:-true}" == "true" ]]; then
    hash=$(openssl rand -hex $((HASH_LENGTH/2)))
  else
    printf -v hash "%0${HASH_LENGTH}x" "$HASH_COUNTER"
    HASH_COUNTER=$((HASH_COUNTER + 1))
    echo "$HASH_COUNTER" >"$HASH_PATHNAME"
  fi
}

__relpath() {
  local target="$1"
  local absTarget
  absTarget=$(realpath "$target" 2>/dev/null || readlink -f "$target")
  echo ".${absTarget#$PWD}"
}

__createPath() {
  local path
  while :; do
    __generateHash
    path="$STORAGE_FILENAME/${hash:0:2}/${hash:2:2}/${hash:4:2}/${hash:6:2}/${hash:8:2}/${hash:10:2}"
    if [[ ! -e "$path" ]] && ! grep -qxF "$path" "$TRACK_PATHNAME" 2>/dev/null; then
      echo "$path"
      return
    fi
  done
}

__trackPath() {
  local relPath
  relPath=$(__relpath "$1")
  mkdir -p "$(dirname "$TRACK_PATHNAME")"
  grep -qxF "$relPath" "$TRACK_PATHNAME" 2>/dev/null || echo "$relPath" >>"$TRACK_PATHNAME"
}

__untrackPath() {
  local relPath
  relPath=$(__relpath "$1")
  if [[ -f "$TRACK_PATHNAME" ]]; then
    grep -vxF "$relPath" "$TRACK_PATHNAME" >"$TRACK_PATHNAME.tmp"
    mv -f "$TRACK_PATHNAME.tmp" "$TRACK_PATHNAME"
  fi
}

__cleanStorage() {
  local dir="$1"
  while [[ "$dir" != "$STORAGE_FILENAME" && "$dir" != "." ]]; do
    if [[ -d "$dir" && -z "$(ls -A "$dir")" ]]; then
      rmdir "$dir"
      dir="$(dirname "$dir")"
    else
      break
    fi
  done
}

__relativePath() {
  local target="$1"
  local base="$2"
  local targetAbs baseAbs commonPart back forward

  targetAbs=$(cd "$(dirname "$target")" && pwd)/"$(basename "$target")"
  baseAbs=$(cd "$base" && pwd)

  commonPart="$baseAbs"
  back=""
  while [[ "${targetAbs#"$commonPart"}" == "$targetAbs" ]]; do
    commonPart="$(dirname "$commonPart")"
    back="../$back"
  done
  forward="${targetAbs#"$commonPart"/}"
  echo "${back}${forward}"
}

# _ln new_link node  # node | category

_ln() {
  local linkName="$1"
  local target="$2"
  local resolved baseDir baseRoot linkBase storageRel dotRootPath relPath

  if [[ ! -e "$target" ]]; then
    echo "Error: target '$target' does not exist"
    return 1
  fi

  resolved=$(realpath "$target" 2>/dev/null || readlink -f "$target")
  if [[ "$resolved" != "$PWD/$STORAGE_FILENAME"/* ]]; then
    echo "Error: target '$target' is not in the storage directory"
    return 1
  fi

  baseDir="$(dirname "$linkName")"
  baseRoot="$baseDir/$ROOT_FILENAME"
  if [[ -L "$baseRoot" ]]; then
    linkBase="$baseRoot"
  else
    linkBase="$ROOT_FILENAME"
  fi

  storageRel="${resolved#$PWD/}"
  dotRootPath="$linkBase/${storageRel#./}"
  relPath=$(__relativePath "$dotRootPath" "$baseDir")
  ln -s "$relPath" "$linkName"
}

# _ls [-l] [-n] [-r] [path]

_ls() {
  local longFormat=false  # -l  Show node hash identifier
  local nodeCount=false   # -n  Show category's node count
  local recursive=false   # -r  List category's childred recursively
  local path="."
  local arg

  while [[ "$#" -gt 0 ]]; do
    arg="$1"
    case "$arg" in
      -l) longFormat=true ;;
      -n) nodeCount=true ;;
      -r) recursive=true ;;
      --) shift; break ;;
      -*) echo "Unknown option: $arg" >&2; return 1 ;;
      *) break ;;
    esac
    shift
  done
  [[ -n "${1:-}" ]] && path="$1"

  __getHashPath() {
    local linkTarget absTarget
    linkTarget=$(readlink "$1")
    absTarget=$(realpath "$linkTarget" 2>/dev/null || readlink -f "$linkTarget")
    if [[ "$absTarget" == "$PWD/$STORAGE_FILENAME"/* ]]; then
      echo "${absTarget#$PWD/$STORAGE_FILENAME/}"
    else
      echo ""
    fi
  }

  __countFiles() {
    local dirLink="$1"
    local targetDir
    targetDir=$(readlink "$dirLink")
    targetDir=$(realpath "$targetDir" 2>/dev/null || readlink -f "$targetDir")
    find "$targetDir" -type f ! -size 0c 2>/dev/null | wc -l
  }

  __listLinks() {
    local dir="$1"
    local indent="$2"
    local item base hash count
    for item in "$dir"/*; do
      [[ ! -L "$item" ]] && continue
      base="$(basename "$item")"
      hash=$(__getHashPath "$item")
      if [[ -d "$item" ]]; then
        if [[ "$longFormat" == true ]]; then
          printf "%s  %s/" "$hash" "$indent$base"
        else
          printf "%s/" "$indent$base"
        fi
        if [[ "$nodeCount" == true ]]; then
          count=$(__countFiles "$item")
          if [[ "$count" -gt 0 ]]; then
            printf " (%d)" "$count"
          fi
        fi
        printf "\n"
        [[ "$recursive" == true ]] && __listLinks "$item" "  $indent"
      else
        if [[ "$longFormat" == true ]]; then
          printf "%s  %s" "$hash" "$indent$base"
        else
          printf "%s" "$indent$base"
        fi
        printf "\n"
      fi
    done
  }

  __listLinks "$path" ""
}

# _mk node  # node only

_mk() {
  local name="$1"
  local path
  path=$(__createPath)
  mkdir -p "$(dirname "$path")"
  touch "$path"
  ln -s "$ROOT_FILENAME/$path" "$name"
  __trackPath "$path"
}

# _mkdir category  # category only

_mkdir() {
  local name="$1"
  local path
  path=$(__createPath)
  mkdir -p "$path"
  local relBackPath
  relBackPath=$(__relativePath "$PWD/$ROOT_FILENAME" "$path")
  ln -s "$relBackPath" "$path/$ROOT_FILENAME"
  ln -s "$ROOT_FILENAME/$path" "$name"
  __trackPath "$path"
}

# _rm node  # node | category

_rm() {
  local name="$1"
  local target absTarget

  if [ ! -L "$name" ]; then
    echo "Error: '$name' is not a symbolic link."
    return 1
  fi

  target=$(readlink "$name")
  absTarget=$(realpath "$target" 2>/dev/null || readlink -f "$target")
  unlink "$name"

  if [[ "$absTarget" == "$PWD/$STORAGE_FILENAME"/* ]]; then
    local hasLinks
    hasLinks=$(find . -type l | while read -r link; do
      local linkTarget resolved
      linkTarget=$(readlink "$link")
      resolved=$(realpath "$linkTarget" 2>/dev/null || readlink -f "$linkTarget")
      echo "$resolved"
    done | grep -xF -- "$absTarget" || true)

    if [[ -z "$hasLinks" ]]; then
      __untrackPath "$absTarget"
      if [[ -d "$absTarget" ]]; then
        rm -rf "$absTarget"
      else
        rm -f "$absTarget"
      fi
      __cleanStorage "$(dirname "$absTarget")"
    fi
  fi
}

# _storage [-s]

_storage() {
  local sortByName=false
  if [[ "${1:-}" == "-s" ]]; then
    sortByName=true
  fi

  find . -type l | while read -r link; do
    local target absTarget relPath name
    target=$(readlink "$link")
    absTarget=$(realpath "$target" 2>/dev/null || readlink -f "$target")
    if [[ "$absTarget" == "$PWD/$STORAGE_FILENAME"/* ]]; then
      relPath=${absTarget#$PWD/$STORAGE_FILENAME/}
      name=$(basename "$link")
      echo "$relPath  $name"
    fi
  done | sort -u |
  if $sortByName; then
    sort -k2,2
  else
    sort
  fi | awk '{ print $1"  "$2 }'
}

__initialize
