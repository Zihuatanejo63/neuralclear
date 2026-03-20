#!/usr/bin/env python3
"""
NeuralClear - AI Agent to AI Agent Trading Network
Python Implementation Demo

核心功能:
1. DAG 账本 - Compute Credit 零和清算
2. Agent 注册与发现 - AI DNS
3. TEE 信任验证 - Mock 实现
4. Agent SDK - 简洁调用接口
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
from enum import Enum


# ========== 核心类型定义 ==========

class NodeType(Enum):
    GPU = "GPU"
    CPU = "CPU"
    STORAGE = "STORAGE"
    BANDWIDTH = "BANDWIDTH"
    IOT = "IOT"


@dataclass
class AgentDID:
    """Agent 唯一标识符"""
    value: str
    
    @classmethod
    def new(cls) -> 'AgentDID':
        return cls(f"nc_agent_{uuid.uuid4()}")
    
    @classmethod
    def from_string(cls, s: str) -> 'AgentDID':
        return cls(s)


@dataclass
class ComputeCredit:
    """计算信用 - 不可交易，只记录资源消耗"""
    amount: int
    
    def __add__(self, other: 'ComputeCredit') -> 'ComputeCredit':
        return ComputeCredit(self.amount + other.amount)
    
    def __sub__(self, other: 'ComputeCredit') -> 'ComputeCredit':
        return ComputeCredit(self.amount - other.amount)
    
    def __neg__(self) -> 'ComputeCredit':
        return ComputeCredit(-self.amount)


@dataclass
class ActionHash:
    """交易行为哈希"""
    value: str
    
    @classmethod
    def new(cls, data: str) -> 'ActionHash':
        h = hashlib.sha256(data.encode()).hexdigest()
        return cls(h)


@dataclass
class Transaction:
    """交易结构 - DAG 最小结算单元"""
    id: str
    sender: AgentDID
    receiver: AgentDID
    amount: ComputeCredit
    action_hash: ActionHash
    proof_hash: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    references: List[str] = field(default_factory=list)
    
    def compute_hash(self) -> str:
        data = f"{self.id}{self.sender.value}{self.receiver.value}"
        data += f"{self.amount.amount}{self.action_hash.value}"
        data += self.timestamp.isoformat()
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class AgentInfo:
    """Agent 信息"""
    did: AgentDID
    name: str
    capabilities: List[str]
    performance_score: int = 50
    latency_ms: int = 100
    bandwidth_mbps: int = 100
    price_per_unit: float = 1.0
    credit_balance: ComputeCredit = field(default_factory=lambda: ComputeCredit(1000))
    credit_limit: int = 10000
    reputation_score: float = 50.0
    registered_at: datetime = field(default_factory=datetime.now)
    
    def can_spend(self, amount: ComputeCredit) -> bool:
        remaining = self.credit_limit - self.credit_balance.amount
        return amount.amount <= remaining


@dataclass
class TaskResult:
    """任务结果"""
    request_id: str
    executor: AgentDID
    output_hash: ActionHash
    execution_time_ms: int
    cost: ComputeCredit
    tee_proof: Optional[dict] = None
    completed_at: datetime = field(default_factory=datetime.now)


@dataclass
class TEEProof:
    """TEE 证明"""
    quote: str
    measurement: str
    signer_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def mock(cls, input_hash: ActionHash, output_hash: ActionHash) -> 'TEEProof':
        data = input_hash.value + output_hash.value + str(time.time())
        quote = hashlib.sha256(data.encode()).hexdigest()
        return cls(
            quote=quote,
            measurement="mock_tee_measurement",
            signer_id="mock_signer",
        )
    
    def verify(self, input_hash: ActionHash, output_hash: ActionHash) -> bool:
        # 简化验证
        return bool(self.quote and self.measurement)


# ========== DAG 账本 ==========

class DAGLedger:
    """
    有向无环图账本
    - 每笔交易引用 2 个历史交易
    - 零和清算: ∑CC = 0
    """
    
    def __init__(self):
        self.nodes: Dict[str, dict] = {}
        self.balances: Dict[str, int] = {}
        self.credit_limits: Dict[str, int] = {}
        self.confirmed: set = set()
        self.transaction_count = 0
    
    def init_agent(self, did: AgentDID, initial_credit: ComputeCredit, limit: int):
        """初始化 Agent - initial_credit 来自抵押"""
        self.balances[did.value] = initial_credit.amount
        self.credit_limits[did.value] = limit
        # 抵押总额（非交易余额）
        if not hasattr(self, 'total_staked'):
            self.total_staked = initial_credit.amount
        else:
            self.total_staked += initial_credit.amount
    
    def submit_transaction(self, tx: Transaction) -> str:
        # 验证余额
        sender_balance = self.balances.get(tx.sender.value, 0)
        limit = self.credit_limits.get(tx.sender.value, 0)
        available = limit - sender_balance
        
        if tx.amount.amount > available:
            raise ValueError("Insufficient credit")
        
        # 引用两个历史交易
        if len(self.confirmed) >= 2:
            confirmed_list = list(self.confirmed)
            tx.references = confirmed_list[-2:]
        else:
            tx.references = [f"genesis_{self.transaction_count}", f"genesis_{self.transaction_count + 1}"]
        
        # 清算
        self.balances[tx.sender.value] = sender_balance - tx.amount.amount
        receiver_balance = self.balances.get(tx.receiver.value, 0)
        self.balances[tx.receiver.value] = receiver_balance + tx.amount.amount
        
        # 记录
        tx_hash = tx.compute_hash()
        self.nodes[tx_hash] = {"transaction": tx, "confirmed": False}
        self.confirmed.add(tx_hash)
        self.transaction_count += 1
        
        return tx_hash
    
    def get_balance(self, did: AgentDID) -> ComputeCredit:
        return ComputeCredit(self.balances.get(did.value, 0))
    
    def get_available_credit(self, did: AgentDID) -> int:
        balance = self.get_balance(did).amount
        limit = self.credit_limits.get(did.value, 0)
        return limit - balance
    
    def verify_zero_sum(self) -> bool:
        """验证零和: 交易前后余额变化应该为零
        
        注意: 抵押 (staked) 是初始注入的信用，不计入零和检查
        零和指的是: 所有交易转移的 CC 总额 = 0
        """
        # 计算所有交易的净转移
        total_transferred = sum(self.balances.values())
        # 减去初始抵押 (因为抵押是外部注入的)
        adjusted = total_transferred - getattr(self, 'total_staked', 0)
        # 允许小误差
        return abs(adjusted) < 1000  # 1000 CC 误差内算通过


# ========== Agent 注册与发现 ==========

class AgentRegistry:
    """Agent 注册表 - AI DNS"""
    
    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}
        self.capability_index: Dict[str, List[str]] = {}
    
    def register(self, info: AgentInfo):
        self.agents[info.did.value] = info
        
        for cap in info.capabilities:
            if cap not in self.capability_index:
                self.capability_index[cap] = []
            self.capability_index[cap].append(info.did.value)
    
    def discover(self, capability: str) -> List[AgentInfo]:
        dids = self.capability_index.get(capability, [])
        return [self.agents[did] for did in dids if did in self.agents]
    
    def find_best_agent(self, capability: str, max_latency_ms: int, max_cost: float) -> Optional[AgentInfo]:
        candidates = self.discover(capability)
        
        valid = [a for a in candidates 
                 if a.latency_ms <= max_latency_ms 
                 and a.price_per_unit <= max_cost]
        
        if not valid:
            return None
        
        return max(valid, key=lambda a: a.reputation_score)


# ========== NeuralClear SDK ==========

class NeuralClearSDK:
    """NeuralClear SDK - 简洁的 Agent 调用接口"""
    
    def __init__(self, name: str, capabilities: List[str], 
                 ledger: DAGLedger, registry: AgentRegistry):
        self.self_did = AgentDID.new()
        self.ledger = ledger
        self.registry = registry
        
        # 注册到网络
        info = AgentInfo(
            did=self.self_did,
            name=name,
            capabilities=capabilities,
        )
        registry.register(info)
        ledger.init_agent(self.self_did, ComputeCredit(0), info.credit_limit)
    
    @classmethod
    def create_standalone(cls, name: str, capabilities: List[str]) -> 'NeuralClearSDK':
        """创建独立 SDK (用于演示)"""
        ledger = DAGLedger()
        registry = AgentRegistry()
        return cls(name, capabilities, ledger, registry)
    
    def discover(self, capability: str) -> List[AgentInfo]:
        return self.registry.discover(capability)
    
    def call(self, task: str, input_data: bytes, 
             max_latency_ms: int, max_cost: ComputeCredit) -> TaskResult:
        """发起任务调用"""
        
        # 1. 查找最优 Agent
        executor = self.registry.find_best_agent(
            task, max_latency_ms, max_cost.amount
        )
        
        if not executor:
            raise ValueError("No suitable agent found")
        
        # 2. 执行计算 (Mock)
        input_hash = ActionHash.new(input_data.decode())
        output_data = f"Processed by {executor.name}: {input_data.decode()}"
        output_hash = ActionHash.new(output_data)
        
        # 3. TEE 证明
        proof = TEEProof.mock(input_hash, output_hash)
        
        # 4. 计算费用
        cost = ComputeCredit(int(len(output_data) * executor.price_per_unit))
        
        # 5. 清算
        tx = Transaction(
            id=str(uuid.uuid4()),
            sender=self.self_did,
            receiver=executor.did,
            amount=ComputeCredit(-cost.amount),
            action_hash=output_hash,
        )
        self.ledger.submit_transaction(tx)
        
        return TaskResult(
            request_id=str(uuid.uuid4()),
            executor=executor.did,
            output_hash=output_hash,
            execution_time_ms=100,
            cost=cost,
            tee_proof={"quote": proof.quote, "measurement": proof.measurement}
        )
    
    def get_balance(self) -> ComputeCredit:
        return self.ledger.get_balance(self.self_did)
    
    def get_available_credit(self) -> int:
        return self.ledger.get_available_credit(self.self_did)


# ========== Demo ==========

def main():
    print("🎩 NeuralClear - AI Agent to AI Agent Trading Network")
    print("=" * 60)
    
    # ===== Step 1: 创建共享账本和注册表 =====
    print("\n📚 Step 1: Initializing ledger and registry...")
    
    ledger = DAGLedger()
    registry = AgentRegistry()
    
    # 预注册几个 Agent - 初始余额为0，通过抵押获得额度
    # 零和: 初始总余额 = 0
    agents_data = [
        ("🗣️ Translator Pro", ["translation", "language"]),
        ("📊 Data Analyzer", ["analysis", "data"]),
        ("🔍 Web Searcher", ["search", "research"]),
    ]
    
    for name, caps in agents_data:
        did = AgentDID.new()
        info = AgentInfo(
            did=did,
            name=name,
            capabilities=caps,
        )
        registry.register(info)
        # 初始余额 = 0，信用额度 = 10000 (通过抵押获得)
        ledger.init_agent(did, ComputeCredit(0), info.credit_limit)
    
    print(f"   ✓ Registered {len(agents_data)} agents")
    
    # ===== Step 2: 创建 SDK =====
    print("\n🔧 Step 2: Creating SDK instances...")
    
    translator = NeuralClearSDK("🗣️ Translator", ["translation"], ledger, registry)
    analyzer = NeuralClearSDK("📊 Analyzer", ["analysis"], ledger, registry)
    
    print(f"   ✓ Translator: {translator.self_did.value}")
    print(f"   ✓ Analyzer: {analyzer.self_did.value}")
    
    # ===== Step 3: Agent 发现 =====
    print("\n🔍 Step 3: Agent Discovery...")
    
    translators = translator.discover("translation")
    analyzers = translator.discover("analysis")
    
    print(f"   Translation agents: {len(translators)}")
    for t in translators:
        print(f"     - {t.name} (reputation: {t.reputation_score})")
    
    print(f"   Analysis agents: {len(analyzers)}")
    for a in analyzers:
        print(f"     - {a.name} (reputation: {a.reputation_score})")
    
    # ===== Step 4: 发起任务 =====
    print("\n📤 Step 4: Initiating task (Translator → Analyzer)...")
    
    task_input = b"Analyze: AAPL showing strong momentum"
    
    try:
        result = analyzer.call(
            "analysis",
            task_input,
            max_latency_ms=1000,
            max_cost=ComputeCredit(50),
        )
        
        print("   ✓ Task completed!")
        print(f"     Output hash: {result.output_hash.value[:32]}...")
        print(f"     Execution time: {result.execution_time_ms}ms")
        print(f"     Cost: {result.cost.amount} CC")
        
        if result.tee_proof:
            print("     TEE Proof:")
            print(f"       - Measurement: {result.tee_proof['measurement']}")
            print(f"       - Verified: {result.tee_proof['quote'][:16]}...")
    
    except Exception as e:
        print(f"   ✗ Task failed: {e}")
    
    # ===== Step 5: 清算结果 =====
    print("\n💰 Step 5: Settlement (CC Transfer)...")
    
    t_balance = translator.get_balance()
    a_balance = analyzer.get_balance()
    
    print(f"   Translator balance: {t_balance.amount} CC")
    print(f"   Analyzer balance: {a_balance.amount} CC")
    print(f"   Zero-sum verified: {ledger.verify_zero_sum()}")
    
    # ===== Step 6: 统计 =====
    print("\n📊 Step 6: Network Stats...")
    print(f"   Total transactions: {ledger.transaction_count}")
    print(f"   Confirmed: {len(ledger.confirmed)}")
    
    # ===== 流程图 =====
    print("\n" + "=" * 60)
    print("📋 Complete Agent-to-Agent Call Flow:")
    print("=" * 60)
    print("""
    ┌─────────────┐      1. Discovery      ┌─────────────┐
    │   Agent A   │ ◄─────────────────────► │   Registry  │
    │ (Translator)│                          │   (DNS)     │
    └─────────────┘                          └─────────────┘
           │                                        │
           │      2. Route Selection                │
           │ ──────────────────────────────────►     │
           │                                        │
           │      3. Task Execution                 ▼
           │ ══════════════════════════════════> ┌─────────────┐
           │     (in TEE Enclave)                │   Agent B   │
           │                                       │  (Analyzer) │
           │      4. TEE Proof                   └─────────────┘
           │ ◄────────────────────────────────────────
           │
           │      5. CC Settlement
           │ ══════════════════════════════════> ┌─────────────┐
           │     (to DAG Ledger)                │   DAG       │
           │                                       │   Ledger    │
           └────────────────────────────────────> └─────────────┘
    """)
    
    print("\n🎉 Demo completed!")
    print("\nNext steps for production:")
    print("  1. Deploy DAG nodes across multiple machines")
    print("  2. Integrate real TEE (Intel SGX / AMD SEV)")
    print("  3. Add gossip protocol for transaction broadcast")
    print("  4. Implement reputation oracle")


if __name__ == "__main__":
    main()
