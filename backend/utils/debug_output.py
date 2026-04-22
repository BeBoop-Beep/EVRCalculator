"""
Debug output wrapper for controlled debug printing.

This module provides a centralized mechanism to manage debug output across the application.
Debug messages can be suppressed globally via the DEBUG_MODE environment variable without
removing print statements from the codebase.

Environment Variables:
    DEBUG_MODE: Set to "1" to enable debug output, "0" (default) to suppress tagged debug prints

Usage:
    from backend.utils.debug_output import debug_print
    
    # These will be suppressed when DEBUG_MODE is "0":
    debug_print("[SIM_POOL_DEBUG] Processing pool: my_pool")
    debug_print("[CALC_POOL_DEBUG] Value: 123")
    
    # These will always print (no debug tags):
    debug_print("Final result: 456")
    debug_print("[ERROR] Something failed")
"""

import os


# Debug tags that should be suppressed when DEBUG_MODE is off
DEBUG_TAGS = {
    "[POOL_INPUT_PROFILE]",
    "[SIM_POOL_DEBUG]",
    "[SIM_POOL_AUDIT]",
    "[SIM_TIMING]",
    "[SIM_ENGINE]",
    "[DB_INPUT_DIAGNOSTICS]",
    "[DB_INPUT_ROW_AUDIT]",
    "[CALC_POOL_DEBUG]",
    "[RARITY_EV_AUDIT]",
    "[RARITY_EV_BUCKETS]",
    "[CARDS_NORMALIZATION_DEBUG]",
    "[DATA_PREP_DATAFRAME_PREVIEW]",
}


def debug_print(message: str) -> None:
    """
    Print a message, optionally suppressing debug-tagged output.
    
    Lines containing any of the defined DEBUG_TAGS are suppressed when DEBUG_MODE
    environment variable is set to "0" (the default). All other lines are always printed.
    
    Args:
        message: The message to print
        
    Returns:
        None
        
    Examples:
        >>> # With DEBUG_MODE="0" (default), this will be suppressed:
        >>> debug_print("[SIM_POOL_DEBUG] Processing pool")
        
        >>> # With DEBUG_MODE="0", this will always print:
        >>> debug_print("Final result: 42")
        
        >>> # With DEBUG_MODE="1", both will print
    """
    debug_mode = os.environ.get("DEBUG_MODE", "0")
    
    # If debug mode is off (default), check if message contains a debug tag
    if debug_mode == "0":
        if any(tag in message for tag in DEBUG_TAGS):
            return
    
    # Print all other messages, or all messages if DEBUG_MODE is "1"
    print(message)
