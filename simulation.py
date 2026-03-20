#!/usr/bin/env python3
"""
NeuralClear - Full Network Simulation
模拟整个 NeuralClear 网络的运行
"""

import random
import time
from dataclasses import dataclass
from typing import List, Dict

# 从原始项目中导入
from neuralclear import (
    DAGLedger, AgentRegistry, AgentInfo, AgentDID, ComputeCredit,
    ActionHash, Transaction, TEEProof, TaskResult, NodeType
)


@dataclass
class SimulationConfig:
    """模拟配置"""
    num_agents: int = 10
    num_transactions: int = 50
    capabilities: List[str] = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = [
                "translation", "analysis", "search", 
                "image_recognition", "code_generation", 
                "text_to_speech", "data_processing"
            ]


class NetworkSimulator:
    """网络模拟器"""
    
    def __init__(self, config: SimulationConfig):
        self.config = config
        self.ledger = DAGLedger()
        self.registry = AgentRegistry()
        self.agents: Dict[str, AgentInfo] = {}
        
    def setup_network(self):
        """初始化网络"""
        print("🏗️  Setting up NeuralClear Network...")
        
        # 创建 Agent 能力池
        agent_templates = [
            ("🗣️ Translator Pro", ["translation", "language"]),
            ("📊 Data Analyzer", ["analysis", "data", "visualization"]),
            ("🔍 Web Searcher", ["search", "research"]),
            ("🖼️ Vision AI", ["image_recognition", "object_detection"]),
            ("💻 Code Generator", ["code_generation", "debugging"]),
            ("🎤 Voice AI", ["text_to_speech", "speech_to_text"]),
            ("📈 Finance Bot", ["stock_analysis", "prediction"]),
            ("🧪 Science Lab", ["data_processing", "simulation"]),
            ("🌐 Multi-Lingual", ["translation", "localization"]),
            ("📝 Writing Assistant", ["text_generation", "summarization"]),
        ]
        
        # 注册 Agent
        for i in range(self.config.num_agents):
            template = agent_templates[i % len(agent_templates)]
            did = AgentDID(f"nc_agent_{i:04d}")
            
            # 随机性能参数
            latency = random.randint(10, 500)
            price = round(random.uniform(0.1, 5.0), 2)
            reputation = round(random.uniform(30, 100), 1)
            
            info = AgentInfo(
                did=did,
                name=f"{template[0]} #{i}",
                capabilities=template[1],
                performance_score=random.randint(40, 100),
                latency_ms=latency,
                bandwidth_mbps=random.randint(50, 1000),
                price_per_unit=price,
                reputation_score=reputation,
                credit_limit=random.randint(5000, 50000),
            )
            
            self.registry.register(info)
            
            # 初始抵押充值
            staked = random.randint(1000, 10000)
            self.ledger.init_agent(did, ComputeCredit(staked), info.credit_limit)
            info.credit_balance = ComputeCredit(staked)
            
            self.agents[did.value] = info
        
        print(f"   ✓ Registered {len(self.agents)} agents")
        print(f"   ✓ Total staked: {self.ledger.total_staked} CC")
        
    def run_transactions(self):
        """运行交易模拟"""
        print(f"\n📡 Running {self.config.num_transactions} transactions...")
        
        successful = 0
        failed = 0
        
        for i in range(self.config.num_transactions):
            # 随机选择调用方
            caller_did = random.choice(list(self.agents.keys()))
            caller = self.agents[caller_did]
            
            # 随机选择需要的能力
            capability = random.choice(self.config.capabilities)
            
            # 查找提供该能力的 Agent
            providers = self.registry.discover(capability)
            if not providers:
                failed += 1
                continue
                
            # 过滤掉自己
            providers = [p for p in providers if p.did.value != caller_did]
            if not providers:
                failed += 1
                continue
                
            # 选择最优 (信誉 + 延迟)
            provider = max(providers, key=lambda a: a.reputation_score / a.latency_ms)
            
            # 执行任务
            try:
                self.execute_task(caller, provider, capability)
                successful += 1
                
                if (i + 1) % 10 == 0:
                    print(f"   Progress: {i+1}/{self.config.num_transactions} "
                          f"(✓{successful} ✗{failed})")
                    
            except Exception as e:
                failed += 1
                
            # 模拟网络延迟
            time.sleep(0.01)
        
        print(f"\n   Final: ✓ {successful} successful, ✗ {failed} failed")
        return successful, failed
    
    def execute_task(self, caller: AgentInfo, provider: AgentInfo, task: str):
        """执行单个任务"""
        # 1. 准备输入
        input_data = f"Task: {task} | Data: {random.randint(1000, 9999)}"
        input_hash = ActionHash.new(input_data)
        
        # 2. Mock 计算
        output_data = f"Result for {task}: {random.random()}"
        output_hash = ActionHash.new(output_data)
        
        # 3. TEE 证明
        proof = TEEProof.mock(input_hash, output_hash)
        
        # 4. 计算费用
        cost = int(len(output_data) * provider.price_per_unit)
        
        # 5. 清算
        tx = Transaction(
            id=f"tx_{random.randint(100000, 999999)}",
            sender=caller.did,
            receiver=provider.did,
            amount=ComputeCredit(-cost),
            action_hash=output_hash,
        )
        
        self.ledger.submit_transaction(tx)
        
        # 6. 更新 Agent 余额
        caller.credit_balance = self.ledger.get_balance(caller.did)
        provider.credit_balance = self.ledger.get_balance(provider.did)
        
        # 7. 更新信誉 (模拟)
        provider.reputation_score = min(100, provider.reputation_score + 0.1)
        
    def generate_report(self):
        """生成网络报告"""
        print("\n" + "=" * 60)
        print("📊 NeuralClear Network Report")
        print("=" * 60)
        
        # 基本统计
        print(f"\n🔢 Network Statistics:")
        print(f"   Total Agents: {len(self.agents)}")
        print(f"   Total Transactions: {self.ledger.transaction_count}")
        print(f"   Confirmed: {len(self.ledger.confirmed)}")
        print(f"   Total Staked: {self.ledger.total_staked} CC")
        
        # 余额分布
        balances = [self.ledger.get_balance(a.did).amount for a in self.agents.values()]
        print(f"\n💰 Balance Distribution:")
        print(f"   Min: {min(balances)} CC")
        print(f"   Max: {max(balances)} CC")
        print(f"   Avg: {sum(balances)/len(balances):.0f} CC")
        print(f"   Zero-sum check: {self.ledger.verify_zero_sum()}")
        
        # Top Agents
        sorted_agents = sorted(
            self.agents.values(), 
            key=lambda a: a.reputation_score, 
            reverse=True
        )
        
        print(f"\n🏆 Top 5 Agents (by reputation):")
        for i, a in enumerate(sorted_agents[:5], 1):
            balance = self.ledger.get_balance(a.did).amount
            print(f"   {i}. {a.name}")
            print(f"      Reputation: {a.reputation_score:.1f} | "
                  f"Balance: {balance} CC | "
                  f"Latency: {a.latency_ms}ms")
        
        # 能力分布
        print(f"\n🔌 Capability Distribution:")
        caps_count = {}
        for a in self.agents.values():
            for cap in a.capabilities:
                caps_count[cap] = caps_count.get(cap, 0) + 1
        
        for cap, count in sorted(caps_count.items(), key=lambda x: -x[1]):
            bar = "█" * count
            print(f"   {cap:20s} {bar} ({count})")
        
        # 交易示例
        print(f"\n📝 Sample Transaction:")
        sample_tx = list(self.ledger.nodes.values())[0].get('transaction')
        if sample_tx:
            print(f"   ID: {sample_tx.id}")
            print(f"   From: {sample_tx.sender.value[:20]}...")
            print(f"   To: {sample_tx.receiver.value[:20]}...")
            print(f"   Amount: {sample_tx.amount.amount} CC")
            print(f"   References: {sample_tx.references}")
        
        print("\n" + "=" * 60)
        print("✅ Simulation Complete")
        print("=" * 60)


def main():
    print("🎩 NeuralClear Full Network Simulation")
    print("=" * 60)
    
    config = SimulationConfig(
        num_agents=10,
        num_transactions=50,
    )
    
    simulator = NetworkSimulator(config)
    
    # 1. 初始化网络
    simulator.setup_network()
    
    # 2. 运行交易
    simulator.run_transactions()
    
    # 3. 生成报告
    simulator.generate_report()


if __name__ == "__main__":
    main()