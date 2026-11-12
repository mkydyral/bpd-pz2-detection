// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Vault} from "./Vault.sol";

/// @notice Легитимные пакетные выплаты: несколько выводов из Vault в одной транзакции.
contract Payroll {
    Vault public immutable vault;
    address public immutable owner;

    constructor(Vault vault_) {
        vault = vault_;
        owner = msg.sender;
    }

    function fund() external payable {
        vault.deposit{value: msg.value}();
    }

    function pay(address[] calldata recipients, uint256[] calldata amounts) external {
        require(msg.sender == owner, "not owner");
        require(recipients.length == amounts.length, "length mismatch");
        for (uint256 i = 0; i < recipients.length; i++) {
            vault.withdrawTo(recipients[i], amounts[i]);
        }
    }
}
