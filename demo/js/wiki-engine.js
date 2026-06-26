/**
 * Aether-Agent v2 — Wiki 引擎 (前端独立模块)
 *
 * 模块化设计: 每个功能独立函数, 易维护, 易测试。
 * 与 Python 后端 (app/core/wiki/) 算法 1:1 对齐。
 *
 * 模块结构:
 *   - Fact 模型 + 内容哈希去重
 *   - 双语正则事实提取器
 *   - Markdown 渲染/解析 (无损往返)
 *   - 相关性评分 (子串 + Jaccard)
 *   - WikiStore (localStorage 持久化)
 *   - 知识组织器 (按主题/标签/时间分组)
 */

const AetherWiki = (function () {
  "use strict";

  // ========== 1. Fact 数据模型 (对应 models.py) ==========

  /**
   * 创建一个 Fact 实例 (不可变)
   * id 由内容哈希自动生成, 保证同一事实不会重复存储。
   */
  function createFact(subject, predicate, object, source, confidence, tags) {
    return {
      id: factId(subject, predicate, object),
      subject: subject,
      predicate: predicate,
      object: object,
      source: source || "extracted",
      confidence: confidence != null ? confidence : 0.7,
      created_at: Date.now() / 1000,
      tags: tags || [],
    };
  }

  /**
   * 内容哈希: SHA1[:16] 的前端等价实现。
   * Python 版用 hashlib.sha1, 这里用 djb2 变体 (demo 用途, 不要求密码学强度)。
   */
  function factId(subject, predicate, obj) {
    var payload = (subject + "|" + predicate + "|" + obj).toLowerCase();
    var hash = 0;
    for (var i = 0; i < payload.length; i++) {
      hash = ((hash << 5) - hash + payload.charCodeAt(i)) | 0;
    }
    return (hash >>> 0).toString(16).padStart(8, "0").slice(0, 16);
  }

  // ========== 2. 双语正则事实提取器 (对应 extractor.py) ==========

  var EXTRACT_PATTERNS = [
    [/(?:my name is|i am|i'm)\s+([A-Z][a-z]+)/i, "user", "name"],
    [/(?:my name is|我叫|我是)\s+(\S+)/i, "user", "name"],
    [/i\s+(?:prefer|like|love)\s+(.+?)(?:[.!?,]|$)/i, "user", "prefers"],
    [/i\s+(?:use|work with|develop in)\s+(.+?)(?:[.!?,]|$)/i, "user", "uses"],
    [/i\s+(?:work at|join|am from)\s+(.+?)(?:[.!?,]|$)/i, "user", "affiliation"],
    [/remember\s+(?:that\s+)?(.+?)(?:[.!?,]|$)/i, "user", "fact"],
    [/(?:the\s+)?project uses\s+(.+?)(?:[.!?,]|$)/i, "project", "uses"],
    [/(?:the\s+)?project is\s+(?:a\s+|an\s+)?(.+?)(?:[.!?,]|$)/i, "project", "is"],
    [/(?:the\s+)?project targets\s+(.+?)(?:[.!?,]|$)/i, "project", "targets"],
    [/(?:we|the team)\s+(?:use|adopt|choose)\s+(.+?)(?:[.!?,]|$)/i, "team", "uses"],
    [/deployment is on\s+(.+?)(?:[.!?,]|$)/i, "ops", "deploy_target"],
    [/(?:api|rate limit|timeout|quota)\s+is\s+(.+?)(?:[.!?,]|$)/i, "config", "value"],
  ];

  /**
   * 从对话轮次中提取事实 (去重)。
   * @param {string[]} turns 对话消息数组
   * @param {number} confidence 置信度 [0,1]
   * @returns {Fact[]} 去重后的事实列表
   */
  function extractFromTurns(turns, confidence) {
    var facts = {};
    var conf = confidence != null ? confidence : 0.7;
    for (var i = 0; i < turns.length; i++) {
      var turn = turns[i];
      for (var j = 0; j < EXTRACT_PATTERNS.length; j++) {
        var pattern = EXTRACT_PATTERNS[j][0];
        var subject = EXTRACT_PATTERNS[j][1];
        var predicate = EXTRACT_PATTERNS[j][2];
        var regex = new RegExp(pattern.source, pattern.flags);
        var match;
        while ((match = regex.exec(turn)) !== null) {
          var value = match[1].trim();
          if (!value || value.length > 200) continue;
          var fact = createFact(subject, predicate, value, "extracted", conf);
          facts[fact.id] = fact;
        }
      }
    }
    return Object.values(facts);
  }

  // ========== 3. Markdown 渲染/解析 (对应 store.py) ==========

  function renderMarkdown(subject, facts) {
    var lines = ["# " + subject, ""];
    for (var i = 0; i < facts.length; i++) {
      var f = facts[i];
      var tagStr = f.tags.length > 0 ? "  [" + f.tags.join(", ") + "]" : "";
      lines.push("- " + f.predicate + ": " + f.object + tagStr);
    }
    return lines.join("\n") + "\n";
  }

  function parseMarkdown(content) {
    var facts = [];
    var subject = "";
    var lines = content.split("\n");
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (line.startsWith("# ")) {
        subject = line.slice(2).trim();
      } else if (line.startsWith("- ") && subject) {
        var body = line.slice(2);
        var tags = [];
        if (body.endsWith("]") && body.indexOf("[") !== -1) {
          var bracket = body.lastIndexOf("[");
          tags = body.slice(bracket + 1, -1).split(",").map(function (t) {
            return t.trim();
          }).filter(Boolean);
          body = body.slice(0, bracket).trimEnd();
        }
        if (body.indexOf(": ") !== -1) {
          var idx = body.indexOf(": ");
          var predicate = body.slice(0, idx).trim();
          var obj = body.slice(idx + 2).trim();
          facts.push(createFact(subject, predicate, obj, "parsed", 1.0, tags));
        }
      }
    }
    return facts;
  }

  // ========== 4. 相关性评分 (对应 store.py _relevance) ==========

  function relevance(fact, text) {
    var textLower = text.toLowerCase();
    var blob = (fact.subject + " " + fact.predicate + " " + fact.object).toLowerCase();
    if (fact.object.toLowerCase().indexOf(textLower) !== -1 || textLower.indexOf(fact.object.toLowerCase()) !== -1) {
      return 1.0;
    }
    var queryTokens = new Set(textLower.split(/\s+/).filter(Boolean));
    var factTokens = new Set(blob.split(/\s+/).filter(Boolean));
    if (queryTokens.size === 0 || factTokens.size === 0) return 0;
    var overlap = 0;
    queryTokens.forEach(function (t) { if (factTokens.has(t)) overlap++; });
    var union = queryTokens.size + factTokens.size - overlap;
    return Math.round((overlap / union) * 1000) / 1000;
  }

  // ========== 5. WikiStore (localStorage 持久化) ==========

  var WIKI_KEY = "aether_wiki_store_v2";

  function WikiStore() {
    this._index = [];
    this._load();
  }

  WikiStore.prototype._load = function () {
    try {
      var data = JSON.parse(localStorage.getItem(WIKI_KEY) || "{}");
      this._index = data.facts || [];
    } catch (e) {
      this._index = [];
    }
  };

  WikiStore.prototype._save = function () {
    try {
      localStorage.setItem(WIKI_KEY, JSON.stringify({ facts: this._index }));
    } catch (e) { /* 忽略配额错误 */ }
  };

  WikiStore.prototype.init = function () { this._load(); return this._index.length; };
  WikiStore.prototype.addFact = function (fact) {
    for (var i = 0; i < this._index.length; i++) {
      if (this._index[i].id === fact.id) return false;
    }
    this._index.push(fact);
    this._save();
    return true;
  };
  WikiStore.prototype.addFacts = function (facts) {
    var added = 0;
    for (var i = 0; i < facts.length; i++) {
      if (this.addFact(facts[i])) added++;
    }
    return added;
  };
  WikiStore.prototype.query = function (text, limit) {
    limit = limit || 10;
    var scored = [];
    for (var i = 0; i < this._index.length; i++) {
      var s = relevance(this._index[i], text);
      if (s > 0) scored.push({ fact: this._index[i], score: s });
    }
    scored.sort(function (a, b) { return b.score - a.score; });
    return scored.slice(0, limit);
  };
  WikiStore.prototype.listFacts = function (subject) {
    if (!subject) return this._index.slice();
    return this._index.filter(function (f) { return f.subject === subject; });
  };
  WikiStore.prototype.listSubjects = function () {
    var seen = {};
    var out = [];
    for (var i = 0; i < this._index.length; i++) {
      var s = this._index[i].subject;
      if (!seen[s]) { seen[s] = true; out.push(s); }
    }
    return out;
  };
  WikiStore.prototype.exportMarkdown = function () {
    var docs = {};
    var subjects = this.listSubjects();
    for (var i = 0; i < subjects.length; i++) {
      var facts = this._index.filter(function (f) { return f.subject === subjects[i]; });
      docs[subjects[i]] = renderMarkdown(subjects[i], facts);
    }
    return docs;
  };
  WikiStore.prototype.clear = function () { this._index = []; this._save(); };
  WikiStore.prototype.count = function () { return this._index.length; };

  // ========== 6. 知识组织器 (网页端展示用) ==========

  /**
   * 按主题分组事实, 返回结构化知识树。
   * 用于 Wiki 页面的侧边栏导航渲染。
   */
  function organizeBySubject(facts) {
    var tree = {};
    for (var i = 0; i < facts.length; i++) {
      var f = facts[i];
      if (!tree[f.subject]) tree[f.subject] = [];
      tree[f.subject].push(f);
    }
    return tree;
  }

  /**
   * 按时间线排序事实 (最新的在前)。
   */
  function sortByTime(facts) {
    return facts.slice().sort(function (a, b) { return b.created_at - a.created_at; });
  }

  /**
   * 统计信息: 主题数、事实数、来源分布、平均置信度。
   */
  function stats(facts) {
    var subjects = {};
    var sources = {};
    var confSum = 0;
    for (var i = 0; i < facts.length; i++) {
      subjects[facts[i].subject] = (subjects[facts[i].subject] || 0) + 1;
      sources[facts[i].source] = (sources[facts[i].source] || 0) + 1;
      confSum += facts[i].confidence;
    }
    return {
      factCount: facts.length,
      subjectCount: Object.keys(subjects).length,
      subjects: subjects,
      sources: sources,
      avgConfidence: facts.length > 0 ? Math.round((confSum / facts.length) * 100) / 100 : 0,
    };
  }

  // ========== 公共 API ==========
  return {
    createFact: createFact,
    factId: factId,
    extractFromTurns: extractFromTurns,
    renderMarkdown: renderMarkdown,
    parseMarkdown: parseMarkdown,
    relevance: relevance,
    WikiStore: WikiStore,
    organizeBySubject: organizeBySubject,
    sortByTime: sortByTime,
    stats: stats,
  };
})();
