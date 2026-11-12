// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @title Хранилище ETH (учебный контракт BPD 2024, ПЗ2)
/// @notice Контракт содержит две намеренные уязвимости. В задании они не исправляются:
/// задача - обнаружить их эксплуатацию по событиям и состоянию блокчейна.
contract Vault is Ownable, Pausable {
    mapping(address => uint256) public balanceOf;
    /// @notice Оператор может выводить средства на обслуживание протокола (sweep).
    address public operator;
    /// @notice Guardian может поставить хранилище на паузу при инциденте.
    address public guardian;

    event Deposit(address indexed account, uint256 amount);
    event Withdrawal(address indexed account, address indexed to, uint256 amount);
    event OperatorChanged(address indexed previousOperator, address indexed newOperator, address indexed by);
    event Swept(address indexed to, uint256 amount);

    constructor(address guardian_) Ownable(msg.sender) {
        guardian = guardian_;
        operator = msg.sender;
    }

    function deposit() external payable whenNotPaused {
        require(msg.value > 0, "zero amount");
        balanceOf[msg.sender] += msg.value;
        emit Deposit(msg.sender, msg.value);
    }

    function withdraw(uint256 amount) external whenNotPaused {
        withdrawTo(msg.sender, amount);
    }

    function withdrawTo(address to, uint256 amount) public whenNotPaused {
        require(balanceOf[msg.sender] >= amount, "insufficient balance");
        balanceOf[msg.sender] -= amount;
        _send(to, amount);
        emit Withdrawal(msg.sender, to, amount);
    }

    /// @notice Вывести весь баланс.
    /// Уязвимость 1: внешний вызов до обнуления баланса - повторный вход (reentrancy).
    function withdrawAll() external whenNotPaused {
        uint256 amount = balanceOf[msg.sender];
        require(amount > 0, "nothing to withdraw");
        
        balanceOf[msg.sender] = 0;
        emit Withdrawal(msg.sender, msg.sender, amount);
        
        _send(msg.sender, amount);
    }

    /// @notice Сменить оператора.
    /// Уязвимость 2: нет проверки onlyOwner - оператором может назначить себя кто угодно.
    function setOperator(address newOperator) external onlyOwner { // <-- ДОБАВЛЕН onlyOwner
        emit OperatorChanged(operator, newOperator, msg.sender);
        operator = newOperator;
    }

    function sweep(address to, uint256 amount) external whenNotPaused {
        require(msg.sender == operator, "not operator");
        _send(to, amount);
        emit Swept(to, amount);
    }

    function pause() external {
        require(msg.sender == guardian || msg.sender == owner(), "not guardian");
        _pause();
    }

    function unpause() external onlyOwner {
        _unpause();
    }

    function _send(address to, uint256 amount) private {
        (bool ok,) = to.call{value: amount}("");
        require(ok, "send failed");
    }
}
