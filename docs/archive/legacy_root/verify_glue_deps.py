#!/usr/bin/env python3
"""
AWS Glue Dependency Verification Script
========================================
Purpose: Validate that all critical dependencies can be imported and function
         correctly before deploying to AWS Glue.

This is your "REPL loop" - catching issues locally instead of waiting for
Glue job failures.
"""

import sys
import traceback
from pathlib import Path


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


def log_test(msg):
    print(f"{Colors.BLUE}[TEST]{Colors.NC} {msg}")


def log_success(msg):
    print(f"{Colors.GREEN}✓{Colors.NC} {msg}")


def log_error(msg):
    print(f"{Colors.RED}✗{Colors.NC} {msg}")


def log_warn(msg):
    print(f"{Colors.YELLOW}⚠{Colors.NC} {msg}")


def verify_import(module_name, package_name=None):
    """
    Attempt to import a module and return success status.
    
    Args:
        module_name: The module to import
        package_name: Display name (defaults to module_name)
    
    Returns:
        (bool, str): (success, version_or_error)
    """
    display_name = package_name or module_name
    try:
        mod = __import__(module_name)
        version = getattr(mod, '__version__', 'unknown')
        log_success(f"{display_name} {version}")
        return True, version
    except ImportError as e:
        log_error(f"{display_name}: {e}")
        return False, str(e)
    except Exception as e:
        log_error(f"{display_name}: Unexpected error: {e}")
        return False, str(e)


def test_xarray_functionality():
    """Test xarray can create and manipulate datasets"""
    log_test("Testing xarray functionality...")
    try:
        import xarray as xr
        import numpy as np
        
        # Create a simple dataset
        data = xr.Dataset({
            'temperature': (('x', 'y'), np.random.rand(3, 4)),
            'pressure': (('x', 'y'), np.random.rand(3, 4))
        }, coords={'x': [0, 1, 2], 'y': [0, 1, 2, 3]})
        
        # Basic operations
        mean_temp = data['temperature'].mean().values
        assert mean_temp is not None
        
        log_success(f"xarray: Created dataset, computed mean={mean_temp:.4f}")
        return True
    except Exception as e:
        log_error(f"xarray functionality test failed: {e}")
        traceback.print_exc()
        return False


def test_cfgrib_functionality():
    """Test cfgrib can be initialized (without actual GRIB file)"""
    log_test("Testing cfgrib functionality...")
    try:
        import cfgrib
        
        # Test that eccodes bindings work
        # This will fail if eccodes shared libraries are missing
        from cfgrib import messages
        
        log_success("cfgrib: Initialized successfully (eccodes bindings OK)")
        return True
    except Exception as e:
        log_error(f"cfgrib functionality test failed: {e}")
        log_warn("This usually means eccodes shared libraries (.so) are missing")
        traceback.print_exc()
        return False


def test_eccodes_functionality():
    """Test eccodes Python bindings"""
    log_test("Testing eccodes functionality...")
    try:
        import eccodes
        
        # Check library version
        version = eccodes.codes_get_api_version()
        log_success(f"eccodes: API version {version}")
        return True
    except Exception as e:
        log_error(f"eccodes functionality test failed: {e}")
        traceback.print_exc()
        return False


def test_pandas_pyarrow():
    """Test pandas with pyarrow backend"""
    log_test("Testing pandas + pyarrow...")
    try:
        import pandas as pd
        import pyarrow as pa
        
        # Create DataFrame and convert to Arrow
        df = pd.DataFrame({
            'a': [1, 2, 3],
            'b': ['x', 'y', 'z']
        })
        
        table = pa.Table.from_pandas(df)
        assert len(table) == 3
        
        log_success(f"pandas {pd.__version__} + pyarrow {pa.__version__}: OK")
        return True
    except Exception as e:
        log_error(f"pandas/pyarrow test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all verification tests"""
    print("=" * 70)
    print("AWS Glue Dependency Verification")
    print("=" * 70)
    
    # Track results
    results = {}
    
    # 1. Import tests
    print("\n[1/2] Import Verification")
    print("-" * 70)
    
    critical_imports = [
        ('xarray', None),
        ('cfgrib', None),
        ('eccodes', None),
        ('numpy', None),
        ('pandas', None),
        ('pyarrow', None),
    ]
    
    for module, display_name in critical_imports:
        success, info = verify_import(module, display_name)
        results[module] = success
    
    # 2. Functionality tests
    print("\n[2/2] Functionality Tests")
    print("-" * 70)
    
    results['xarray_func'] = test_xarray_functionality()
    results['cfgrib_func'] = test_cfgrib_functionality()
    results['eccodes_func'] = test_eccodes_functionality()
    results['pandas_pyarrow_func'] = test_pandas_pyarrow()
    
    # Summary
    print("\n" + "=" * 70)
    total = len(results)
    passed = sum(results.values())
    failed = total - passed
    
    if failed == 0:
        log_success(f"All {total} tests passed! ✓")
        print("=" * 70)
        print()
        return 0
    else:
        log_error(f"{failed}/{total} tests failed")
        print("=" * 70)
        print("\nFailed tests:")
        for name, success in results.items():
            if not success:
                print(f"  - {name}")
        print()
        return 1


if __name__ == '__main__':
    sys.exit(main())
