#!/usr/bin/env bash

# This script removes what is not compatible with Python3.6

# Here we substitute the f-strings of the form {xxx = } with xxx = {xxx}
sed -r 's/f"\{(.*?)\ =\}"/f"\1 = {\1}"/g' ciak.py > ciak36.py

# Here we remove type hints
sed -i 's/:\ tuple\[str\]//g' ciak36.py
sed -i 's/:\ bool//g' ciak36.py
sed -i 's/:\ str//g' ciak36.py

sed -i 's/:\ tuple\[str, ...\]//g' ciak36.py
sed -i 's/:\ dict\[str, str\]//g' ciak36.py

sed -i 's/->\ tuple\[str, ...\]//g' ciak36.py
sed -i 's/->\ None//g' ciak36.py
sed -i 's/->\ str//g' ciak36.py
