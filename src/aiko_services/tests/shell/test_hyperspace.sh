#!/usr/bin/env bash
#
# Usage
# ~~~~~
# mkdir test;  cd test  # Start with an empty "test/" directory
# ./test_hyperspace.sh  [-i shell | python]
#
# To Do
# ~~~~~
# - Test HyperSpace commands work correctly, when "cd" into child directories
#
# - Rebuild "geekscape/" including "ReadMe.md" files
#
# - Implement parsing MarkDown files including ServiceDefinition JSON or LISP
#   - Change tests to use "def_xx.json" --> "def_xx.md"

export HYPERSPACE_RANDOM_HASH=false  # repeatable diagnosis and testing

PREFIX=""
SOURCE=hyperspace
TEST_ALL=false  # skip "rm" tests

while [[ $# -gt 0 ]]; do
  case "$1" in
    -a|--all)
      TEST_ALL=true  # include "rm" tests
      shift
      ;;
    -i|--implementation)
      shift
      case "$1" in
        shell)
          PREFIX="_"
          source ../../../../../scripts/${SOURCE}.sh
          ;;
        python)
          PREFIX="aiko_hyperspace "
          ;;
        *)
          echo "Error: Invalid implementation '$1', use shell or python" >&2
          exit 1
          ;;
      esac
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [-i shell|python]"
      exit 0
      ;;
    *)
      echo "Error: Unknown option '$1'" >&2
      echo "Usage: $0 [-i shell|python]" >&2
      exit 1
      ;;
  esac
done

PREFIX=${PREFIX:-"aiko_hyperspace "}

# -----------------------------------------------------------------------------

echo "### ${PREFIX}ls ###"
${PREFIX}ls

printf "\n### ${PREFIX}mk def_00.json ###\n"
${PREFIX}mk def_00.json
cat >def_00.json <<EOF
{"name": "def_00.json"}
EOF

printf "\n### ${PREFIX}ln def_01.json def_00.json ###\n"
${PREFIX}ln def_01.json def_00.json
cat def_01.json

printf "\n### ${PREFIX}mkdir cat_a ###\n"
${PREFIX}mkdir cat_a

printf "\n### ${PREFIX}mk cat_a/def_a0.json ###\n"
${PREFIX}mk cat_a/def_a0.json
cat >cat_a/def_a0.json <<EOF
{"name": "cat_a/def_a0.json"}
EOF

printf "\n### ${PREFIX}ln cat_a/def_a1.json def_00.json ###\n"
${PREFIX}ln cat_a/def_a1.json def_00.json
cat cat_a/def_a1.json

printf "\n### ${PREFIX}ln cat_a/def_a2.json cat_a/def_a0.json ###\n"
${PREFIX}ln cat_a/def_a2.json cat_a/def_a0.json
cat cat_a/def_a2.json

printf "\n### ${PREFIX}ln cat_b cat_a ###\n"
${PREFIX}ln cat_b cat_a

printf "\n### ${PREFIX}ls -l -n -r ###\n"
${PREFIX}ls -l -n -r

printf "\n### ${PREFIX}storage -s ###\n"
${PREFIX}storage -s

# -----------------------------------------------------------------------------

if [[ "$TEST_ALL" == true ]]; then
  printf "\n### ${PREFIX}rm def_00.json ###\n"
  ${PREFIX}rm def_00.json
  cat def_01.json

  printf "\n### ${PREFIX}rm cat_a ###\n"
  ${PREFIX}rm cat_a

  printf "\n### ${PREFIX}ls -l -n -r ###\n"
  ${PREFIX}ls -l -n -r

  printf "\n### ${PREFIX}ls -l -n -r cat_b ###\n"
  ${PREFIX}ls -l -n -r cat_b

  printf "\n### ${PREFIX}storage -s ###\n"
  ${PREFIX}storage -s
fi

# -----------------------------------------------------------------------------
