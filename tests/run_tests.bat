@echo off
REM DataLens Test Runner - Windows Batch Script
REM Ensures tests run in the datalens conda environment

echo ====================================================================
echo DataLens Test Runner
echo ====================================================================
echo Activating datalens conda environment...
echo.

REM Activate the datalens conda environment
call conda activate datalens
if errorlevel 1 (
    echo ERROR: Failed to activate datalens conda environment
    echo Make sure conda is installed and the 'datalens' environment exists
    echo.
    echo To create the environment, run:
    echo   conda create -n datalens python=3.11
    echo   conda activate datalens
    echo   pip install -r ../requirements.txt
    pause
    exit /b 1
)

echo Environment activated successfully
echo.

REM Run the Python test runner with all arguments passed through
python run_tests.py %*

REM Capture the exit code
set TEST_EXIT_CODE=%errorlevel%

echo.
echo ====================================================================
echo Tests completed with exit code: %TEST_EXIT_CODE%
echo ====================================================================

REM Deactivate conda environment
call conda deactivate

REM Exit with the test exit code
exit /b %TEST_EXIT_CODE%
