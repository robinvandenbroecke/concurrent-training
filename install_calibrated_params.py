"""
Install calibrated observation mapping parameters as operational source of truth.
"""
import sys
sys.path.insert(0, '/root/clawd/projects/concurrent-training')

from pathlib import Path
from app.domain.observation_mapping import load_mapping_params
from app.services.observation_mapping_service import install_calibrated_params


def main():
    print("Installing calibrated observation mapping parameters...")
    
    # Load the calibrated params from v4
    calibrated_path = "./artifacts/synth_v2_run_v4/calibrated_mapping_params.json"
    
    if not Path(calibrated_path).exists():
        print(f"Error: Calibrated params not found at {calibrated_path}")
        print("Run sprint_v4_calibration.py first")
        return
    
    params = load_mapping_params(calibrated_path)
    
    print(f"Loaded calibrated params:")
    print(f"  a = {params.a}")
    print(f"  b_l = {params.b_l}")
    print(f"  b_sys = {params.b_sys}")
    print(f"  b_t = {params.b_t}")
    
    # Install as operational config
    target_path = "./artifacts/config/observation_mapping_params.json"
    installed_path = install_calibrated_params(params, target_path=target_path)
    
    print(f"\nInstalled to: {installed_path}")
    print("\nThis config is now the operational source of truth for:")
    print("  - replay/validation")
    print("  - production day-level predictions")
    print("  - any path using predict_perf_y_operational()")


if __name__ == "__main__":
    main()
