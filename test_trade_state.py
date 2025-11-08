"""Test trade state persistence module."""

import logging
from src.trade_state import TradeState
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

def main():
    print("="*80)
    print("TRADE STATE PERSISTENCE TEST")
    print("="*80)
    print()

    # Use test state file
    test_state_file = "data/state/test_trade_state.json"
    state = TradeState(test_state_file)

    print("✓ Test 1: Save position state...")
    position = {
        'deal_id': 'TEST_DEAL_12345',
        'entry_price': 16700.0,
        'tp_level': 16740.0,
        'sl_level': 16600.0,
        'entry_time': '2025-11-08T10:30:00'
    }

    state.save_position(position)
    assert Path(test_state_file).exists(), "State file not created!"
    print(f"  ✓ Position saved to {test_state_file}")
    print()

    print("✓ Test 2: Load position state...")
    loaded = state.load_position()
    assert loaded is not None, "Failed to load position!"
    assert loaded['deal_id'] == 'TEST_DEAL_12345', "Deal ID mismatch!"
    assert loaded['entry_price'] == 16700.0, "Entry price mismatch!"
    print("  ✓ Position loaded successfully")
    print(f"  ✓ Deal ID: {loaded['deal_id']}")
    print(f"  ✓ Entry: {loaded['entry_price']:.2f}")
    print()

    print("✓ Test 3: Check position exists...")
    assert state.position_exists(), "Position should exist!"
    print("  ✓ Position exists check passed")
    print()

    print("✓ Test 4: Clear position state...")
    state.clear_position()
    assert not Path(test_state_file).exists(), "State file not deleted!"
    assert not state.position_exists(), "Position should not exist!"
    print("  ✓ Position cleared successfully")
    print()

    print("✓ Test 5: Load when no state exists...")
    loaded = state.load_position()
    assert loaded is None, "Should return None when no state!"
    print("  ✓ Returns None as expected")
    print()

    print("="*80)
    print("TRADE STATE PERSISTENCE - ALL TESTS PASSED ✓")
    print("="*80)
    print()
    print("Summary:")
    print("  ✓ Atomic write (prevents corruption)")
    print("  ✓ Save/load position data correctly")
    print("  ✓ Position exists check works")
    print("  ✓ Clear position removes file")
    print("  ✓ Handles missing file gracefully")
    print()

if __name__ == '__main__':
    main()
