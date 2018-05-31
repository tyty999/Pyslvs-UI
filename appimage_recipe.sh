# This is a very simple example on how to bundle a Python application as an AppImage
# using virtualenv and AppImageKit using Ubuntu
# NOTE: Please test the resulting AppImage on your target systems and copy in any additional
# libraries and/or dependencies that might be missing on your target system(s).

########################################################################
# Create the AppDir
########################################################################

APP=pyslvs
LOWERAPP=${APP,,}

mkdir -p ENV/$APP.AppDir/
cd ENV/$APP.AppDir/

########################################################################
# Create a virtualenv inside the AppDir
########################################################################

mkdir -p usr
virtualenv --always-copy --python=python3 ./usr

#Copy other modules.
cp /usr/lib/python3.5/ssl.py ./usr/lib/python3.5/ssl.py

source usr/bin/activate

# Source some helper functions
wget -q https://raw.githubusercontent.com/AppImage/AppImages/master/functions.sh -O ./functions.sh
. ./functions.sh

mkdir -p usr/bin/

#Show python and pip versions
python --version
pip --version

# Install python dependencies into the virtualenv
pip install -r ../../requirements.txt

deactivate

########################################################################
# "Install" app in the AppDir
########################################################################

cp ../../launch_pyslvs.py usr/bin/$LOWERAPP
sed -i "1i\#!/usr/bin/env python" usr/bin/$LOWERAPP
chmod a+x usr/bin/$LOWERAPP

cp ../../icons_rc.py usr/bin
cp ../../preview_rc.py usr/bin
cp -r ../../core usr/bin
rm -fr usr/bin/core/libs/pyslvs/build
rm -fr usr/bin/core/libs/python_solvespace/obj
rm -fr usr/bin/core/libs/python_solvespace/iclude
rm -fr usr/bin/core/libs/python_solvespace/src
find . -type f -name '*.ui' -delete
find usr/bin/core/libs/pyslvs/ -type f -name '*.pyx' -delete
find usr/bin/core/libs/ -type f -name '*.c' -delete

########################################################################
# Finalize the AppDir
########################################################################

get_apprun

cd ../..
VERSION=$(python3 -c "from core.info.info import __version__; print(\"{}.{}.{}\".format(*__version__))")
cd ENV/$APP.AppDir/

cat > $LOWERAPP.desktop <<EOF
[Desktop Entry]
Name=$APP
Exec=$LOWERAPP
Type=Application
Icon=$LOWERAPP
Comment=Open Source Planar Linkage Mechanism Simulation and Dimensional Synthesis System.
EOF

# Make the AppImage ask to "install" itself into the menu
get_desktopintegration $LOWERAPP
cp ../../icons/main_big.png $LOWERAPP.png

########################################################################
# Bundle dependencies
########################################################################

copy_deps ; copy_deps ; copy_deps
delete_blacklisted
move_lib

########################################################################
# Package the AppDir as an AppImage
########################################################################

cd ..
generate_appimage
