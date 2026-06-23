/**
 * Aether-Agent v2 — 路由引擎前端实现 (JS 移植版)
 *
 * 这是 app/core/routing/ 下 Python 实现的 1:1 移植，用于网页端 demo。
 * 保持算法一致性：signals -> scorer -> feedback -> policy -> RoutingDecision
 */

// ========== Tier 枚举与模型映射 (对应 tiers.py) ==========
const Tier = {
  PARSE: { value: 1, name: "PARSE", label: "本地轻量模型", model: "llama3:8b", color: "#06b6d4" },
  CHAT: { value: 2, name: "CHAT", label: "快速模型", model: "gpt-4o-mini", color: "#10b981" },
  COMPLEX: { value: 3, name: "COMPLEX", label: "强力模型", model: "gpt-4o", color: "#a855f7" },
};

const DEFAULT_PARSE_MAX = 35;
const DEFAULT_CHAT_MAX = 55;

function tierForScore(score, parseMax = DEFAULT_PARSE_MAX, chatMax = DEFAULT_CHAT_MAX) {
  if (score <= parseMax) return Tier.PARSE;
  if (score <= chatMax) return Tier.CHAT;
  return Tier.COMPLEX;
}

// ========== 关键词词表 (对应 signals.py 模块级常量) ==========
const CODE_KEYWORDS = [
  "def ", "class ", "import ", "return ", "async ", "await ", "function",
  "const ", "let ", "var ", "SELECT ", "FROM ", "WHERE ", "println!", "print(",
  "console.log", "fmt.", "docker", "kubernetes", "git ", "python", "javascript",
  "typescript", "rust", "golang", "algorithm", "api ", "endpoint", "database",
  "server", "implement", "interface", "abstract", "inheritance",
];

const QUESTION_WORDS = [
  "?", "怎么", "如何", "为什么", "怎么办", "吗？", "吗?", "why", "how", "what",
  "when", "where", "which", "who", "explain", "could you", "can you", "please",
  "is it", "are there", "what's",
];

const COMPLEXITY_WORDS = [
  "分析", "对比", "权衡", "权衡利弊", "总结", "梳理", "设计", "重构", "架构",
  "步进", "分步骤", "推理", "证明", "优化", "analyze", "compare", "trade-off",
  "tradeoff", "summarize", "design", "refactor", "architect", "step-by-step",
  "step by step", "reason", "optimize", "evaluate", "diagnose",
];

const COMMAND_WORDS = [
  "翻译", "提取", "解析", "转成", "转码", "格式化", "命名", "translate",
  "extract", "parse", "convert", "format", "rename", "summarize this",
];

const CONVERSATION_WORDS = [
  "你好", "嗨", "早上好", "晚上好", "谢谢", "辛苦", "再见", "拜拜",
  "hello", "hi", "hey", "thanks", "thank you", "morning", "bye",
];

const LISTING_MARKERS = ["1.", "2.", "3.", "- ", "* ", "•", "、", "；", "; ", " and ", " or ", "，以及"];

// ========== 信号提取器 (对应 signals.py) ==========

function countMatches(message, needles) {
  const low = message.toLowerCase();
  return needles.reduce((acc, kw) => acc + (low.includes(kw.toLowerCase()) ? 1 : 0), 0);
}

function lengthSignal(message) {
  const n = message.length;
  let contrib;
  if (n < 30) {
    contrib = -0.5 + (n / 30.0) * 0.5;
  } else {
    const k = 350.0;
    contrib = n / (n + k);
  }
  return { name: "length", raw: n, contribution: Math.round(contrib * 1000) / 1000, note: `${n} chars` };
}

function codeSignal(message) {
  let raw = 0;
  if (message.includes("```")) raw += 2;
  // 4+ 空格缩进行
  const indentMatches = message.match(/^\s{4,}\S/gm);
  if (indentMatches) raw += indentMatches.length;
  raw += countMatches(message, CODE_KEYWORDS);
  const contrib = Math.min(1.0, raw * 0.4);
  return { name: "code", raw, contribution: Math.round(contrib * 1000) / 1000, note: `${raw} code markers` };
}

function questionSignal(message) {
  const raw = countMatches(message, QUESTION_WORDS);
  const contrib = Math.min(0.6, raw * 0.3);
  return { name: "question", raw, contribution: Math.round(contrib * 1000) / 1000, note: `${raw} question markers` };
}

function complexitySignal(message) {
  const raw = countMatches(message, COMPLEXITY_WORDS);
  const contrib = Math.min(1.0, raw * 0.35);
  return { name: "complexity", raw, contribution: Math.round(contrib * 1000) / 1000, note: `${raw} reasoning markers` };
}

function commandSignal(message) {
  const raw = countMatches(message, COMMAND_WORDS);
  if (raw === 0) return { name: "command", raw: 0, contribution: 0, note: "no command verbs" };
  const contrib = message.length <= 200 ? -Math.min(1.0, 0.7 * raw) : 0;
  return { name: "command", raw, contribution: Math.round(contrib * 1000) / 1000, note: `${raw} command verbs` };
}

function conversationSignal(message) {
  let raw = countMatches(message, CONVERSATION_WORDS);
  // emoji 启发式
  let emojiLike = 0;
  for (const ch of message) {
    if (ch.codePointAt(0) > 0x2000 && !/[\x20-\x7E]/.test(ch)) emojiLike++;
  }
  raw += Math.min(3, emojiLike);
  if (raw === 0) return { name: "conversation", raw: 0, contribution: 0, note: "no chat markers" };
  let contrib = -Math.min(0.5, 0.2 * raw);
  if (countMatches(message, COMPLEXITY_WORDS) > 0) contrib = 0;
  return { name: "conversation", raw, contribution: Math.round(contrib * 1000) / 1000, note: `${raw} chat markers` };
}

function multiTopicSignal(message) {
  const sentences = (message.match(/[.!?。！？]/g) || []).length;
  const listMarkers = LISTING_MARKERS.reduce((acc, m) => acc + (message.includes(m) ? 1 : 0), 0);
  const raw = sentences + listMarkers;
  const contrib = Math.min(0.8, raw * 0.15);
  return { name: "multi_topic", raw, contribution: Math.round(contrib * 1000) / 1000, note: `${raw} structural markers` };
}

const SIGNALS = [
  lengthSignal, codeSignal, questionSignal, complexitySignal,
  commandSignal, conversationSignal, multiTopicSignal,
];

function extractAll(message) {
  if (!message || !message.trim()) throw new Error("message must be non-empty");
  return SIGNALS.map((fn) => fn(message));
}

// ========== 评分器 (对应 scorer.py) ==========
const SIGNAL_WEIGHTS = {
  length: 0.12,
  code: 0.20,
  question: 0.10,
  complexity: 0.22,
  command: 0.20,
  conversation: 0.10,
  multi_topic: 0.06,
};

const BASE_SCORE = 40.0;
const SCALE = 48.0;

function score(results) {
  const perSignal = [];
  let weightedSum = 0.0;
  for (const res of results) {
    const weight = SIGNAL_WEIGHTS[res.name];
    if (weight === undefined) throw new Error(`no weight for signal '${res.name}'`);
    const pts = res.contribution * weight;
    weightedSum += pts;
    perSignal.push([res.name, Math.round(pts * 10000) / 10000]);
  }
  let total = BASE_SCORE + weightedSum * SCALE;
  total = Math.max(0, Math.min(100, total));
  return { total: Math.round(total * 100) / 100, perSignal };
}

// ========== 反馈存储 (对应 feedback.py, 简化版用 localStorage) ==========
const MAX_ADJUSTMENT = 15.0;
const STEP = 3.0;
const FEEDBACK_KEY = "aether_feedback_store";

function messageSignature(message) {
  const tokens = message.toLowerCase().split(/\s+/).sort();
  const bag = {};
  for (const t of tokens) bag[t] = (bag[t] || 0) + 1;
  const payload = Object.keys(bag).sort().map((w) => `${w}:${bag[w]}`).join(" ");
  // 简单哈希 (前端不要求密码学强度)
  let hash = 0;
  for (let i = 0; i < payload.length; i++) {
    const ch = payload.charCodeAt(i);
    hash = ((hash << 5) - hash) + ch;
    hash |= 0;
  }
  return (hash >>> 0).toString(16).padStart(8, "0").slice(0, 16);
}

function loadFeedback() {
  try {
    return JSON.parse(localStorage.getItem(FEEDBACK_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveFeedback(store) {
  try {
    localStorage.setItem(FEEDBACK_KEY, JSON.stringify(store));
  } catch {}
}

function recordFeedback(message, positive) {
  const store = loadFeedback();
  const sig = messageSignature(message);
  const delta = positive ? STEP * 0.5 : -STEP;
  const current = store[sig] || 0;
  store[sig] = Math.max(-MAX_ADJUSTMENT, Math.min(MAX_ADJUSTMENT, current + delta));
  saveFeedback(store);
}

function adjustFor(message, scoreValue) {
  const store = loadFeedback();
  const adj = store[messageSignature(message)] || 0;
  if (adj === 0) return scoreValue;
  return Math.max(0, Math.min(100, scoreValue + adj));
}

// ========== 策略引擎 (对应 policy.py, 简化版) ==========
const DEFAULT_POLICY = {
  maxTier: null,
  overrides: [
    { taskType: "coding", projectPhase: "implementation", tier: "COMPLEX", reason: "编码任务需要强推理能力" },
    { taskType: "support", tier: "CHAT", reason: "支持查询不需要强力模型" },
    { userRole: "analyst", tier: "COMPLEX", reason: "分析师角色隐含复杂分析需求" },
    { userRole: "engineer", projectPhase: "planning", tier: "CHAT", reason: "规划讨论属于对话性质" },
  ],
};

function matchOverride(rules, ctx) {
  for (const rule of rules) {
    if (rule.taskType != null && rule.taskType !== ctx.taskType) continue;
    if (rule.projectPhase != null && rule.projectPhase !== ctx.projectPhase) continue;
    if (rule.userRole != null && rule.userRole !== ctx.userRole) continue;
    return rule;
  }
  return null;
}

function applyPolicy(scoreValue, ctx, signalResults, auditReasons) {
  let tier = tierForScore(scoreValue);
  const reasons = [...auditReasons];
  let overridden = false;

  const rule = matchOverride(DEFAULT_POLICY.overrides, ctx);
  if (rule) {
    tier = Tier[rule.tier];
    overridden = true;
    reasons.push(`策略覆盖 -> ${tier.name}: ${rule.reason}`);
  }

  if (DEFAULT_POLICY.maxTier && tier.value > Tier[DEFAULT_POLICY.maxTier].value) {
    tier = Tier[DEFAULT_POLICY.maxTier];
    overridden = true;
    reasons.push(`预算护栏限制为 ${tier.name}`);
  }

  reasons.push(`最终层级 -> ${tier.name} (分数 ${scoreValue.toFixed(1)})`);

  return {
    tier,
    model: tier.model,
    score: scoreValue,
    signalResults,
    auditReasons: reasons,
    overridden,
  };
}

// ========== 路由编排器 (对应 router.py) ==========
function route(message, ctx = {}) {
  const context = {
    userId: ctx.userId || null,
    taskType: ctx.taskType || null,
    projectPhase: ctx.projectPhase || null,
    userRole: ctx.userRole || null,
  };

  // Stage 1: 信号提取
  const signalResults = extractAll(message);

  // Stage 2: 加权评分
  const scoreObj = score(signalResults);
  const audit = [`信号提取 -> 原始分数 ${scoreObj.total.toFixed(1)}`];

  // Stage 3: 自适应反馈调整
  const scoreValue = adjustFor(message, scoreObj.total);
  if (Math.abs(scoreValue - scoreObj.total) > 0.01) {
    audit.push(`反馈调整 -> ${scoreValue.toFixed(1)}`);
  }

  // Stage 4: 策略覆盖 + 预算护栏
  return applyPolicy(scoreValue, context, signalResults, audit);
}

// 导出供 UI 使用
window.AetherEngine = {
  route,
  recordFeedback,
  Tier,
  SIGNAL_WEIGHTS,
  DEFAULT_POLICY,
};
