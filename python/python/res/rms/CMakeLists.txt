set(PYTHON_SOURCES
    __init__.py
    librms.py
    rms.py
)

add_python_package("python.res.rms"  ${PYTHON_INSTALL_PREFIX}/res/rms "${PYTHON_SOURCES}" True)

