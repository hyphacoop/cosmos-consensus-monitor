#!/bin/bash
pylint=0
yamllint=0

if [ ! $CI ]
then
	echo "Auto-formatting python"
	python -m autopep8 --in-place --recursive .

    echo "Linting python"
    python -m pylint server/*.py --disable=E1101,W1203
fi

if [ $CI ]
then
    echo "Linting python"
    python -m pylint server/*.py --disable=W0511,E0401,R0801,E1101,W1203
    if [ $? -ne 0 ]
    then
    	pylint=1
    	echo "Linting python failed"
    fi
fi

if [ $pylint -ne 0 ]
then
	exit 1
fi