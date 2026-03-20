import sys
import os

# Adjust sys.path to run properly
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.agent import agent

def test_contract_scan():
    print("--- 1. Testing address only ---")
    address = "0x1234567890123456789012345678901234567890"
    result1 = agent.process_query(address)
    import json
    print(json.dumps(result1, indent=2))
    
    print("\n--- 2. Testing contract code ---")
    dummy_code = """
    pragma solidity ^0.8.0;
    contract HoneypotToken {
        mapping(address => bool) public isBlacklisted;
        address public owner;
        
        constructor() {
            owner = msg.sender;
        }
        
        function transfer(address to, uint256 amount) public {
            require(!isBlacklisted[msg.sender], "Blacklisted");
            // ... transfer logic
        }
        
        function blacklist(address user) public {
            require(msg.sender == owner, "Only owner");
            isBlacklisted[user] = true;
        }
    }
    """
    result2 = agent.process_query(f"Please audit this contract: {dummy_code}")
    print(json.dumps(result2, indent=2))

if __name__ == "__main__":
    test_contract_scan()
