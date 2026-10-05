/* ==========================================================================
   宝可梦简中卡牌情报站 —— 前端渲染
   数据来自 data/data.js（window.PB_DATA），由 scripts/fetch_data.py 生成
   ========================================================================== */
(function () {
  "use strict";

  var DATA = window.PB_DATA || {};
  var $ = function (id) { return document.getElementById(id); };
  var today = new Date();
  var TODAY = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime();

  /* ------------------------------------------------------------- 工具 */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function d2ts(d) {
    if (!d) return 0;
    var p = String(d).split("-");
    if (p.length !== 3) return 0;
    return new Date(+p[0], +p[1] - 1, +p[2]).getTime();
  }

  function fmtMD(d) {
    if (!d) return "";
    var p = String(d).split("-");
    return p.length === 3 ? (+p[1]) + "月" + (+p[2]) + "日" : d;
  }

  function daysOff(d) {
    var t = d2ts(d);
    if (!t) return null;
    return Math.round((t - TODAY) / 86400000);
  }

  function imgOrPlaceholder(src, alt) {
    if (src) {
      return '<img src="' + esc(src) + '" alt="' + esc(alt || "") + '" loading="lazy">';
    }
    return '<div class="noimg">暂无图片</div>';
  }

  function emptyBox(text) {
    return '<div class="empty">' + esc(text) + "</div>";
  }

  /* -------------------------------------------------- 顶部信息与导航 */
  function renderMeta() {
    var m = DATA.meta || {};
    var next = m.generated_date ? d2ts(m.generated_date) + 7 * 86400000 : 0;
    var nextStr = next
      ? new Date(next).getFullYear() + "-" +
        String(new Date(next).getMonth() + 1).padStart(2, "0") + "-" +
        String(new Date(next).getDate()).padStart(2, "0")
      : "下周一";

    var gc = gymCounts();
    $("meta-bar").innerHTML = [
      '<span class="meta-chip"><span class="dot"></span>数据更新：<b>' +
        esc(m.generated_at || "-") + "</b></span>",
      '<span class="meta-chip">下次更新：<b>' + esc(nextStr) + "</b></span>",
      '<span class="meta-chip">未发售新品 <b>' + visibleProductCount() + "</b> 条</span>",
      '<span class="meta-chip">官方道馆 <b>' + gc.open + "</b> 家</span>",
      (gc.soon ? '<span class="meta-chip">待开业 <b>' + gc.soon + "</b> 家</span>" : ""),
      '<span class="meta-chip">资讯 <b>' + countNews() + "</b> 条</span>"
    ].join("");

    var srcs = (m.sources || []).map(function (s) {
      return '<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.name) + "</a>";
    }).join("");
    $("src-list").innerHTML = srcs;

    $("n-products").textContent = visibleProductCount();
    $("n-events").textContent = (DATA.events || []).length;
    $("n-shops").textContent = gymCounts().open;
    $("n-decks").textContent = ((DATA.decks && DATA.decks.meta) || []).length;
    $("n-regulation").textContent = ((DATA.regulation && DATA.regulation.standard &&
      DATA.regulation.standard.marks) || []).join("·") || "—";
  }

  function countNews() {
    var s = 0;
    s += (DATA.events || []).length;
    s += ((DATA.shops && DATA.shops.news) || []).length;
    s += ((DATA.decks && DATA.decks.news) || []).length;
    return s;
  }

  /* 道馆计数：列表里含「尚未开业」的预开业道馆（not_yet_open），分开统计避免误读 */
  function gymCounts() {
    var gs = (DATA.shops && DATA.shops.gyms) || [];
    var soon = gs.filter(function (g) { return g.not_yet_open; }).length;
    return { total: gs.length, open: gs.length - soon, soon: soon };
  }

  /* 已发售商品默认不再展示，这里统计未发售新品的数量 */
  function visibleProductCount() {
    return ((DATA.products) || []).filter(function (p) {
      return p.release_status === "upcoming";
    }).length;
  }

  /* ------------------------------------------------------- 1. 新品 / 上新 */
  var productFilter = "全部";
  var showReleased = false;   // 已发售商品：默认收纳，按需展开

  function renderProducts() {
    var list = DATA.products || [];
    if (!list.length) {
      $("product-grid").innerHTML = emptyBox("暂无商品数据");
      return;
    }

    // 只展示尚未发售的新品；已发售的收进折叠区
    var upcoming = list.filter(function (p) { return p.release_status === "upcoming"; });
    var released = list.filter(function (p) { return p.release_status !== "upcoming"; });

    var bar = $("released-bar");
    if (bar) {
      bar.innerHTML = (upcoming.length && released.length)
        ? '<button class="released-btn" id="released-toggle">' +
          (showReleased ? "收起已发售商品（" + released.length + " 件）"
                        : "近 3 个月已发售商品 " + released.length + " 件 · 点击展开对照") +
          "</button>"
        : "";
      var tg = $("released-toggle");
      if (tg) {
        tg.onclick = function () { showReleased = !showReleased; renderProducts(); };
      }
    }

    // 没有未发售新品时退回展示已发售，避免栏目空白
    var pool = upcoming.length
      ? (showReleased ? upcoming.concat(released) : upcoming)
      : released;

    var cats = ["全部"];
    pool.forEach(function (p) {
      if (cats.indexOf(p.category) < 0) cats.push(p.category);
    });

    $("product-filters").innerHTML = cats.map(function (c) {
      var n = c === "全部" ? pool.length
        : pool.filter(function (x) { return x.category === c; }).length;
      return '<button class="filter-btn' + (c === productFilter ? " on" : "") +
        '" data-cat="' + esc(c) + '">' + esc(c) + " " + n + "</button>";
    }).join("");

    var view = productFilter === "全部" ? pool
      : pool.filter(function (p) { return p.category === productFilter; });

    $("product-grid").innerHTML = view.map(function (p) {
      var off = p.goods ? daysOff(p.date) : daysOff(p.release_date);
      var badge = "";
      if (p.release_status === "released") {
        badge = '<span class="badge released">已发售</span>';
      } else if (off !== null && off > 0) {
        badge = '<span class="badge soon">' + (off <= 30 ? off + " 天后发售" : "即将发售") + "</span>";
      } else if (off !== null && off >= -21) {
        badge = '<span class="badge new">新上架</span>';
      } else {
        badge = '<span class="badge">' + esc(p.category) + "</span>";
      }

      var rows = "";
      var rel = p.goods ? (p.date || "")
        : (p.release_raw || p.release_date || "待定");
      rows += '<div class="kv"><span class="k">发售</span><span class="v">' + esc(rel) + "</span></div>";
      if (p.price) {
        rows += '<div class="kv"><span class="k">定价</span><span class="v price">' +
          esc(p.price) + "</span></div>";
      }

      // 商品内容中随附的周边：冰箱贴 / 徽章 / 磁吸贴 等
      var bundled = "";
      if (p.bundled && p.bundled.length) {
        bundled = '<div class="bundled">' + p.bundled.map(function (b) {
          return '<span class="bundled-chip">含' + esc(b) + "</span>";
        }).join("") + "</div>";
      }

      var note = p.content
        ? '<div class="card-note">' + esc(p.content) + "</div>" : "";
      var link = p.url
        ? '<a class="card-link" href="' + esc(p.url) + '" target="_blank" rel="noopener">' +
          (p.goods ? "查看官方资讯 →" : "查看官方商品详情 →") + "</a>"
        : "";

      return '<article class="card">' +
        '<div class="card-media">' + imgOrPlaceholder(p.image, p.name) + badge + "</div>" +
        '<div class="card-body">' +
          '<h3 class="card-title">' + esc(p.name) + "</h3>" +
          '<div class="card-date">' + esc(p.category) + "</div>" +
          rows + note + bundled + link +
        "</div></article>";
    }).join("");

    Array.prototype.forEach.call($("product-filters").children, function (btn) {
      btn.onclick = function () {
        productFilter = btn.getAttribute("data-cat");
        renderProducts();
      };
    });
  }

  /* ------------------------------------------------ 通用时间线渲染 */
  function renderTimeline(el, list, emptyText) {
    if (!list || !list.length) { $(el).innerHTML = emptyBox(emptyText || "暂无内容"); return; }
    var sorted = list.slice().sort(function (a, b) {
      return d2ts(b.date) - d2ts(a.date);
    });
    $(el).innerHTML = sorted.slice(0, 40).map(function (it) {
      var cat = (it.category_raw || "").toLowerCase();
      var cls = cat === "event" ? "event" : (cat === "campaign" ? "campaign" : "product");
      var label = it.category_raw || "官方资讯";
      var p = String(it.date || "").split("-");
      var d = p.length === 3 ? p[2] : "--";
      var m = p.length === 3 ? (+p[1]) + "月" : "";

      // 赛事活动会带状态与活动截止日
      var extra = "";
      if (it.status) {
        extra += '<span class="tag shop">' + esc(it.status) + "</span>";
      }
      if (it.end_date) {
        extra += "<span>至 " + esc(it.end_date.slice(5).replace("-", " / ")) + "</span>";
      }

      return '<a class="tl-item" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
        '<div class="tl-date"><div class="d">' + esc(d) + '</div><div class="m">' + esc(m) + "</div></div>" +
        '<div class="tl-thumb">' + imgOrPlaceholder(it.image, it.title) + "</div>" +
        '<div class="tl-main">' +
          '<div class="tl-title">' + esc(it.title) + "</div>" +
          '<div class="tl-meta"><span class="tag ' + cls + '">' + esc(label) + "</span>" +
            "<span>" + esc(it.date || "") + "</span>" + extra + "</div>" +
          (it.summary ? '<div class="tl-summary">' + esc(it.summary) + "</div>" : "") +
        "</div></a>";
    }).join("");
  }

  /* --------------------------------- 活动 / 赛事：默认 5 条，其余收起可展开 */
  var EVENT_SHOW = 5;       // 默认展示条数
  var EVENT_MONTHS = 2;     // 只展示最近 N 个月

  // 只保留最近 N 个月内（含今天之后）的活动
  function withinMonths(list, months) {
    var edge = new Date(today.getFullYear(), today.getMonth() - months, today.getDate()).getTime();
    return list.filter(function (it) {
      var t = d2ts(it.date);
      return t >= edge;                // 有日期且在窗口内
    });
  }

  function renderEventTimeline(el, list, emptyText) {
    var all = withinMonths(list || [], EVENT_MONTHS).slice().sort(function (a, b) {
      return d2ts(b.date) - d2ts(a.date);   // 最新在前
    });

    if (!all.length) {
      $(el).innerHTML = emptyBox(emptyText || "暂无活动");
      if ($("event-more-bar")) $("event-more-bar").hidden = true;
      if ($("event-count")) $("event-count").textContent = "";
      return;
    }

    function itemHTML(it, hidden) {
      var cat = (it.category_raw || "").toLowerCase();
      var cls = cat === "event" ? "event" : (cat === "campaign" ? "campaign" : "product");
      var p = String(it.date || "").split("-");
      var d = p.length === 3 ? p[2] : "--";
      var m = p.length === 3 ? (+p[1]) + "月" : "";
      var extra = "";
      if (it.status) extra += '<span class="tag shop">' + esc(it.status) + "</span>";
      if (it.end_date) {
        extra += "<span>至 " + esc(it.end_date.slice(5).replace("-", " / ")) + "</span>";
      }
      return '<a class="tl-item' + (hidden ? " is-hidden" : "") +
          '" href="' + esc(it.url) + '" target="_blank" rel="noopener">' +
        '<div class="tl-date"><div class="d">' + esc(d) + '</div><div class="m">' + esc(m) + "</div></div>" +
        '<div class="tl-thumb">' +
          // 折叠项去掉懒加载，避免展开瞬间出现图片空白
          (it.image
            ? '<img src="' + esc(it.image) + '" alt="' + esc(it.title || "") + '"' +
              (hidden ? "" : ' loading="lazy"') + ">"
            : '<div class="noimg">暂无图片</div>') +
        "</div>" +
        '<div class="tl-main">' +
          '<div class="tl-title">' + esc(it.title) + "</div>" +
          '<div class="tl-meta"><span class="tag ' + cls + '">' +
            esc(it.category_raw || "官方资讯") + "</span>" +
            "<span>" + esc(it.date || "") + "</span>" + extra + "</div>" +
          (it.summary ? '<div class="tl-summary">' + esc(it.summary) + "</div>" : "") +
        "</div></a>";
    }

    // 全部渲染出来，第 5 条之后默认隐藏，靠 CSS class 控制
    $(el).innerHTML = all.map(function (it, i) {
      return itemHTML(it, i >= EVENT_SHOW);
    }).join("");

    var rest = all.length - EVENT_SHOW;
    if ($("event-count")) {
      $("event-count").textContent = "共 " + all.length + " 条（近 " + EVENT_MONTHS + " 个月）";
    }

    var bar = $("event-more-bar");
    if (!bar) return;

    if (rest <= 0) {
      bar.hidden = true;
      return;
    }
    bar.hidden = false;
    bar.textContent = "展开其余 " + rest + " 条活动 · 点击展开";
    bar.onclick = function () {
      var expanded = bar.getAttribute("data-expanded") === "1";
      Array.prototype.forEach.call($(el).querySelectorAll(".tl-item"), function (n, i) {
        if (i >= EVENT_SHOW) n.classList.toggle("is-hidden", expanded);
      });
      bar.setAttribute("data-expanded", expanded ? "0" : "1");
      bar.textContent = expanded
        ? "展开其余 " + rest + " 条活动 · 点击展开"
        : "收起 · 仅显示最新 " + EVENT_SHOW + " 条";
    };
  }

  /* ------------------------------------------------------- 3. 官方卡牌道馆 */
  function renderShops() {
    var sh = DATA.shops || {};

    // 道馆
    var gt = $("gym-total");
    if (gt) {
      var gc = gymCounts();
      gt.textContent = gc.total
        ? "共 " + gc.open + " 家" + (gc.soon ? " · 待开业 " + gc.soon + " 家" : "")
        : "";
    }
    drawGyms("");

    var input = $("shop-search");
    input.oninput = function () {
      drawGyms(input.value.trim());
      // 搜索清空后回到折叠态
      if (!input.value.trim() && !gymExpanded) drawGyms("");
    };

    var gbar = $("gym-more-bar");
    if (gbar) {
      gbar.onclick = function () {
        gymExpanded = !gymExpanded;
        drawGyms(input.value.trim());
      };
    }

    // 视口变化会改变网格列数，重算「3 行」对应的家数
    var rt;
    window.addEventListener("resize", function () {
      clearTimeout(rt);
      rt = setTimeout(function () {
        if (gymExpanded) return;             // 已展开无需重算
        drawGyms(input.value.trim());
      }, 200);
    });

    renderTimeline("shop-news", sh.news, "近期没有新店预告");
  }

  var gymExpanded = false;   // 道馆折叠状态
  var GYM_ROWS = 3;          // 默认展示行数

  // 网格是 auto-fill 响应式，列数随视口变化，实时读取
  function gymCols() {
    var g = $("shop-grid");
    if (!g) return 1;
    var t = window.getComputedStyle(g).gridTemplateColumns;
    if (!t || t === "none") return 1;
    var n = t.split(" ").filter(function (x) { return x && x !== "0px"; }).length;
    return Math.max(1, n);
  }

  function drawGyms(kw) {
    var gyms = (DATA.shops && DATA.shops.gyms) || [];
    var view = kw
      ? gyms.filter(function (g) {
          return (g.name + " " + (g.address || "") + " " + (g.hours || "") + " " +
            (g.opened || "") + (g.not_yet_open ? "尚未开业" : "")).indexOf(kw) >= 0;
        })
      : gyms;

    if (!view.length) {
      $("shop-grid").innerHTML = emptyBox(kw ? "没有匹配的道馆，换个关键词试试" : "暂无道馆数据");
      if ($("gym-more-bar")) $("gym-more-bar").hidden = true;
      return;
    }

    // 搜索时直接展示全部匹配结果；无搜索时默认收起
    var folding = !kw && !gymExpanded;

    $("shop-grid").innerHTML = view.map(function (g) {
      return '<div class="shop-card clickable' + (g.not_yet_open ? " is-soon" : "") +
        '" data-gym="' + gyms.indexOf(g) + '">' +
        '<div class="shop-thumb">' + imgOrPlaceholder(g.image, g.name) + "</div>" +
        '<div class="shop-info">' +
          '<div class="shop-name">' + esc(g.name) +
            (g.not_yet_open ? '<span class="gym-soon">尚未开业</span>' : "") + "</div>" +
          (g.opened
            ? '<div class="shop-row"><span class="k">开业</span><span>' + esc(g.opened) +
              (g.not_yet_open ? "<b>（尚未开业）</b>" : "") + "</span></div>"
            : "") +
          (g.hours ? '<div class="shop-row"><span class="k">营业</span><span>' + esc(g.hours) + "</span></div>" : "") +
          (g.address ? '<div class="shop-row"><span class="k">地址</span><span>' + esc(g.address) + "</span></div>" : "") +
          (g.grand_gift ? '<div class="shop-row"><span class="k">特典</span><span>' + esc(g.grand_gift) + "</span></div>" : "") +
        "</div></div>";
    }).join("");

    // 道馆卡片点击 → 弹窗展示限定商品
    Array.prototype.forEach.call(
      $("shop-grid").querySelectorAll(".shop-card"), function (el) {
        el.onclick = function () {
          var idx = parseInt(el.getAttribute("data-gym"), 10);
          if (!isNaN(idx)) openGymModal(view[idx]);
        };
      });

    var bar = $("gym-more-bar");
    if (!bar) return;

    // 渲染后读真实列数，按「行」计算折叠位置
    var show = gymCols() * GYM_ROWS;

    if (kw || view.length <= show) { bar.hidden = true; return; }

    if (folding) {
      Array.prototype.forEach.call(
        $("shop-grid").querySelectorAll(".shop-card"), function (n, i) {
          if (i < show) return;
          n.classList.add("is-hidden");
          // 折叠项提前加载图片，避免展开瞬间空白
          var im = n.querySelector("img");
          if (im) im.removeAttribute("loading");
        });
    }

    bar.hidden = false;
    bar.textContent = gymExpanded
      ? "收起 · 只看 " + GYM_ROWS + " 行"
      : "展开其余 " + (view.length - show) + " 家道馆（共 " + view.length + " 家）";
  }

  /* -------------------------------------------------------- 4. 环境牌组 */
  var DECK_SHOW = 5;       // 榜单默认展示条数（Top5）

  function tierClass(t) {
    t = String(t || "");
    if (t.indexOf("核心") === 0) return "t-core";
    if (t.indexOf("一线") === 0) return "t-top";
    if (t.indexOf("二线") === 0) return "t-mid";
    return "t-edge";
  }

  // 潜力标签的配色：高 / 上升 / 稳定 / 待观察 / 低
  function potClass(p) {
    p = String(p || "");
    if (p.indexOf("高") === 0 || p.indexOf("中高") === 0) return "p-high";
    if (p.indexOf("中") === 0) return "p-up";
    if (p.indexOf("稳定") === 0) return "p-steady";
    if (p.indexOf("低") === 0) return "p-low";
    return "p-wait";
  }

  function renderDecks() {
    var a = (DATA.decks && DATA.decks.analysis) || {};
    var list = a.decks || [];

    if (!list.length) {
      $("deck-rank").innerHTML = emptyBox("暂无环境牌组数据");
      return;
    }

    // ——— 分析口径说明 ———
    if ($("deck-source")) {
      var s = a.source || {};
      $("deck-source").innerHTML =
        '数据源：<a href="' + esc(s.url || "#") + '" target="_blank" rel="noopener">' +
        esc(s.name || "AREAZERO.GG") + "</a> · " + esc(s.method || "") +
        (s.sample ? "（样本 " + esc(s.sample) + "）" : "") +
        " · " + esc(a.regulation || "") +
        " · 分析更新 " + esc(a.updated_at || "");
    }
    if ($("deck-metrics")) {
      $("deck-metrics").textContent = a.metrics_explain || "";
    }

    // ——— 环境牌组榜：条长为使用率，默认 Top5，其余收起 ———
    var maxShare = list[0].share || 1;
    $("deck-rank").innerHTML = list.map(function (d, i) {
      var w = Math.max(8, Math.round(d.share * 100 / maxShare));
      var ratio = d.ratio == null ? "—" : d.ratio.toFixed(2);
      var ratioCls = d.ratio == null ? "" :
        (d.ratio >= 1.05 ? " rc-up" : (d.ratio < 0.95 ? " rc-down" : ""));
      return '<div class="rank-row deck-row clickable' + (i >= DECK_SHOW ? " is-hidden" : "") +
          '" data-deck="' + i + '" title="点击看这套牌的拆解">' +
          '<div class="rank-no">' + (i + 1) + "</div>" +
          '<div class="rank-main">' +
            '<div class="rank-name">' +
              '<span class="rank-nm">' + esc(d.name) + "</span>" +
              '<span class="tier-tag ' + tierClass(d.tier) + '">' +
                esc(d.tier || "") + "</span></div>" +
            '<div class="rank-bar"><i style="width:' + w + '%"></i></div>' +
          "</div>" +
          '<div class="rank-num"><b>' + d.share + "%</b>" +
            '<span class="rn-sub">使用率 · 表现分 ' + d.perf_share + "%</span></div>" +
          '<div class="rank-ratio' + ratioCls + '">' + ratio +
            '<span class="rn-sub">转换比</span></div>' +
          '<span class="pot-tag ' + potClass(d.potential) + '">' +
            esc(d.potential || "") + "</span>" +
        "</div>";
    }).join("");

    if ($("deck-meta-count")) {
      $("deck-meta-count").textContent =
        "共 " + list.length + " 套 · 点牌组名看拆解";
    }

    // Top5 之外的收起 / 展开
    var dbar = $("deck-more-bar");
    if (dbar) {
      var drest = list.length - DECK_SHOW;
      if (drest > 0) {
        dbar.hidden = false;
        dbar.textContent = "展开其余 " + drest + " 套";
        dbar.onclick = function () {
          var open = dbar.getAttribute("data-open") === "1";
          Array.prototype.forEach.call(
            $("deck-rank").querySelectorAll(".deck-row"), function (n, i) {
              if (i >= DECK_SHOW) n.classList.toggle("is-hidden", open);
            });
          dbar.setAttribute("data-open", open ? "0" : "1");
          dbar.textContent = open
            ? "展开其余 " + drest + " 套"
            : "收起 · 只看 Top " + DECK_SHOW;
        };
      } else {
        dbar.hidden = true;
      }
    }

    Array.prototype.forEach.call(
      $("deck-rank").querySelectorAll(".deck-row"), function (el) {
        el.onclick = function () {
          openDeckModal(list[parseInt(el.getAttribute("data-deck"), 10)]);
        };
      });

    // ——— 结论区 ———
    if ($("deck-conclusion")) {
      var cs = a.conclusion || [];
      $("deck-conclusion").innerHTML = cs.length
        ? '<h3 class="panel-title">本期研判</h3>' +
          '<div class="concl-list">' +
          cs.map(function (c) { return "<p>" + esc(c) + "</p>"; }).join("") +
          "</div>"
        : "";
    }

    // ——— 尾巴：低使用率牌组说明 ———
    if ($("deck-tail")) {
      $("deck-tail").textContent = a.tail_note || "";
    }

    // ——— 三套核心牌组拆解 ———
    var cores = list.filter(function (d) { return d.detail; }).slice(0, 3);
    if ($("deck-core") && cores.length) {
      $("deck-core").innerHTML = '<h3 class="panel-title">三套核心牌组拆解</h3>' +
        '<div class="core-grid">' + cores.map(function (d) {
          var de = d.detail;
          var li = function (arr) {
            return (arr || []).map(function (x) {
              return "<li>" + esc(x) + "</li>";
            }).join("");
          };
          return '<div class="core-card">' +
            '<div class="cc-head">' +
              '<span class="cc-name">' + esc(d.name) + "</span>" +
              '<span class="cc-role">' + esc(de.role || "") + "</span>" +
            "</div>" +
            '<div class="cc-stats">使用率 <b>' + d.share + "%</b> · 表现分 <b>" +
              d.perf_share + "%</b> · 转换比 <b>" +
              (d.ratio == null ? "—" : d.ratio.toFixed(2)) + "</b> · 样本 <b>" +
              (d.count || 0) + "</b> 份</div>" +
            '<div class="cc-sec">打法</div>' +
            '<p class="cc-text">' + esc(de.gameplan || "") + "</p>" +
            '<div class="cc-sec">优势</div><ul class="cc-list">' + li(de.strengths) + "</ul>" +
            '<div class="cc-sec">短板</div><ul class="cc-list cc-weak">' + li(de.weaknesses) + "</ul>" +
            '<div class="cc-sec">对局</div>' +
            '<p class="cc-text">' + esc(de.matchups || "") + "</p>" +
          "</div>";
        }).join("") + "</div>";
    }

    // ——— 行动建议 ———
    var adv = a.action_advice;
    if ($("deck-advice") && adv && adv.tiers) {
      $("deck-advice").innerHTML =
        '<h3 class="panel-title">怎么选 · 按投入程度对号入座</h3>' +
        '<p class="adv-intro">' + esc(adv.intro || "") + "</p>" +
        '<div class="adv-grid">' + adv.tiers.map(function (t) {
          var ul = function (arr, cls) {
            return '<ul class="adv-list ' + (cls || "") + '">' +
              (arr || []).map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") +
              "</ul>";
          };
          return '<div class="adv-card">' +
            '<div class="adv-top"><span class="adv-level">' + esc(t.level) + "</span>" +
              '<span class="adv-budget">' + esc(t.budget) + "</span></div>" +
            '<div class="adv-label">' + esc(t.label) + "</div>" +
            '<div class="adv-pick">首选：<b>' + esc(t.pick) + "</b></div>" +
            '<div class="adv-sec">为什么</div>' + ul(t.why) +
            '<div class="adv-sec">注意</div>' +
            '<p class="adv-warn">' + esc(t.avoid || "") + "</p>" +
            '<div class="adv-sec">怎么做</div>' + ul(t.steps, "adv-steps") +
          "</div>";
        }).join("") + "</div>" +
        '<p class="adv-disc">' + esc(adv.disclaimer || "") + "</p>";
    }
  }

  /* ------------------------------------------- 牌组详情弹窗（潜力分析） */
  function openDeckModal(d) {
    if (!d) return;
    var html = '<h3 class="modal-title">' + esc(d.name) + "</h3>";

    var ratio = d.ratio == null ? "—" : d.ratio.toFixed(2);
    html += '<div class="modal-stat">' +
      "<span>使用率 <b>" + d.share + "%</b></span>" +
      "<span>表现分占比 <b>" + d.perf_share + "%</b></span>" +
      "<span>转换比 <b>" + ratio + "</b></span>" +
      "<span>样本 <b>" + (d.count || 0) + "</b> 份</span>" +
      "</div>";

    html += '<div class="modal-sec">潜力：' +
      '<span class="pot-tag ' + potClass(d.potential) + '">' +
      esc(d.potential || "") + "</span></div>" +
      '<p class="modal-outlook">' + esc(d.outlook || "") + "</p>";

    var rs = d.reasons || [];
    if (rs.length) {
      html += '<div class="modal-sec">原因</div><div class="modal-list">';
      rs.forEach(function (r) {
        html += '<div class="modal-item reason-item">' + esc(r) + "</div>";
      });
      html += "</div>";
    }

    if (d.risk) {
      html += '<div class="modal-sec">风险</div>' +
        '<div class="modal-risk">' + esc(d.risk) + "</div>";
    }

    // 核心牌组详解（仅前三名有）
    var de = d.detail;
    if (de) {
      var mli = function (arr) {
        return '<div class="modal-list">' + (arr || []).map(function (x) {
          return '<div class="modal-item reason-item">' + esc(x) + "</div>";
        }).join("") + "</div>";
      };
      html += '<div class="modal-sec">定位：' + esc(de.role || "") + "</div>" +
        '<div class="modal-sec">打法</div>' +
        '<p class="modal-outlook">' + esc(de.gameplan || "") + "</p>" +
        '<div class="modal-sec">优势</div>' + mli(de.strengths) +
        '<div class="modal-sec">短板</div>' + mli(de.weaknesses) +
        '<div class="modal-sec">对局</div>' +
        '<p class="modal-outlook">' + esc(de.matchups || "") + "</p>";
    }

    var q = encodeURIComponent(d.name + " 卡组");
    var links = [
      ["AREAZERO.GG 卡组统计（本榜数据源）", "https://tcg.mik.moe/decks"],
      ["B 站搜索该卡组", "https://search.bilibili.com/all?keyword=" + q],
      ["52poke 检索卡面事实", "https://wiki.52poke.com/index.php?search=" + q],
    ];
    html += '<div class="modal-sec">延伸查看</div><div class="modal-links">' +
      links.map(function (l) {
        return '<a class="modal-link" href="' + esc(l[1]) +
          '" target="_blank" rel="noopener">' + esc(l[0]) + " ↗</a>";
      }).join("") + "</div>";

    $("deck-modal-body").innerHTML = html;
    $("deck-modal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeDeckModal() {
    var box = $("deck-modal");
    if (!box) return;
    box.hidden = true;
    document.body.style.overflow = "";
  }

  /* ------------------------------------------- 道馆详情弹窗（限定商品） */
  function openGymModal(g) {
    if (!g) return;
    var html = '<h3 class="modal-title">' + esc(g.name) +
      (g.not_yet_open ? '<span class="gym-soon">尚未开业</span>' : "") + "</h3>";

    // 尚未开业的道馆（官方已公布开业日期）：明确提示，避免误读为已营业
    if (g.not_yet_open) {
      html += '<div class="gym-soon-tip">该道馆尚未开业，官方公布的开幕日期为 <b>' +
        esc(g.opened || "待定") + "</b>。以下信息以官方公告为准，实际以现场为准。</div>";
    }

    // 基本信息
    var info = "";
    if (g.hours) info += '<div class="kv"><span class="k">营业</span><span class="v">' + esc(g.hours) + "</span></div>";
    if (g.closed) info += '<div class="kv"><span class="k">休息日</span><span class="v">' + esc(g.closed) + "</span></div>";
    if (g.address) info += '<div class="kv"><span class="k">地址</span><span class="v">' + esc(g.address) + "</span></div>";
    if (g.opened) {
      info += '<div class="kv"><span class="k">开业</span><span class="v">' + esc(g.opened) +
        (g.not_yet_open ? "（尚未开业）" : "") + "</span></div>";
    }
    if (info) html += '<div class="gym-modal-info">' + info + "</div>";

    // 通用限定商品
    if (g.exclusives && g.exclusives.length) {
      html += '<div class="modal-sec">道馆限定商品</div>';
      html += '<ul class="gym-excl-list">' +
        g.exclusives.map(function (e) {
          return "<li>" + esc(e) + "</li>";
        }).join("") + "</ul>";
    }

    // 开业特典
    if (g.grand_gift) {
      html += '<div class="modal-sec">开业特典</div>';
      html += '<div class="gym-gift-box">' +
        '<div class="gym-gift-name">' + esc(g.grand_gift) + "</div>" +
        (g.grand_gift_note
          ? '<div class="gym-gift-note">' + esc(g.grand_gift_note) + "</div>"
          : "") +
        "</div>";
    }

    // 没有任何限定信息时
    if (!g.exclusives && !g.grand_gift) {
      html += '<div class="modal-outlook">该道馆的限定商品信息暂未收录。</div>';
    }

    html += '<div class="modal-tip">数据来源：52poke 百科「宝可梦官方卡牌道馆」词条，人工维护。</div>';

    $("gym-modal-body").innerHTML = html;
    $("gym-modal").hidden = false;
    document.body.style.overflow = "hidden";
  }

  function closeGymModal() {
    var box = $("gym-modal");
    if (!box) return;
    box.hidden = true;
    document.body.style.overflow = "";
  }

  function initModal() {
    var box = $("deck-modal");
    if (box) {
      var btn = $("deck-modal-close");
      if (btn) btn.onclick = closeDeckModal;
      box.onclick = function (e) { if (e.target === box) closeDeckModal(); };
    }

    var gbox = $("gym-modal");
    if (gbox) {
      var gbtn = $("gym-modal-close");
      if (gbtn) gbtn.onclick = closeGymModal;
      gbox.onclick = function (e) { if (e.target === gbox) closeGymModal(); };
    }

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.key === "Esc") {
        closeDeckModal();
        closeGymModal();
      }
    });
  }

  /* -------------------------------------------------------- 5. 版本 / 赛制 */
  function renderRegulation() {
    var r = DATA.regulation || {};
    var std = r.standard || {};
    var open = r.open || {};

    var html = "";

    // 标准赛制
    if (std.marks && std.marks.length) {
      var marks = std.marks.map(function (mk) {
        return '<div class="mark">' + esc(mk) + "</div>";
      }).join("");
      // 展示被轮替掉的上一代标记（当前可用标记之前的那个字母）作灰色对照
      var first = std.marks[0];
      var all = "ABCDEFGHIJKLMNOP".split("");
      var gi = all.indexOf(first) - 1;
      var gone = (gi >= 0) ? [all[gi]] : [];
      var goneHtml = gone.map(function (mk) {
        return '<div class="mark gone" title="已退出标准赛制">' + esc(mk) + "</div>";
      }).join("");

      html += '<div class="reg-card">' +
        '<div class="reg-head"><h3>标准赛制</h3>' +
          '<div class="sub">' + esc(r.updated_at ? "官方更新日期：" + r.updated_at : "") +
          (std.effective_from ? " · 自 " + std.effective_from + " 起生效" : "") + "</div></div>" +
        '<div class="reg-body">' +
          '<div class="sub-title">当前可用赛制标记</div>' +
          '<div class="marks">' + marks + goneHtml + "</div>" +
          '<div class="mark-note">灰色标记为已退出标准赛制的上一代标记，仅供对照；8 种基本能量卡始终可用。</div>' +
          sectionsHtml(std) +
        "</div></div>";
    }

    // 开放赛制
    if (open.series || (open.sections && open.sections.length)) {
      var chips = (open.series || []).map(function (s) {
        return '<span class="chip">' + esc(s) + "系列</span>";
      }).join("");
      var bans = (open.banned || []).map(function (b) {
        return '<span class="chip ban">' + esc(b) + "</span>";
      }).join("");

      html += '<div class="reg-card">' +
        '<div class="reg-head open"><h3>开放赛制</h3>' +
          '<div class="sub">' + esc(r.updated_at ? "官方更新日期：" + r.updated_at : "") + "</div></div>" +
        '<div class="reg-body">' +
          (chips ? '<div class="sub-title">可使用系列</div><div class="chip-list">' + chips + "</div>" : "") +
          (bans ? '<div class="sub-title">禁用卡牌</div><div class="chip-list">' + bans + "</div>" : "") +
          sectionsHtml(open) +
        "</div></div>";
    }

    $("reg-grid").innerHTML = html || emptyBox("暂无赛制数据");

    renderTimeline("reg-news", r.news, "暂无赛制调整公告");
  }

  function sectionsHtml(block) {
    var secs = block.sections || [];
    if (!secs.length) return "";
    return secs.map(function (s) {
      var body = "";
      (s.texts || []).forEach(function (t) {
        body += '<p class="reg-text">' + esc(t) + "</p>";
      });
      var cards = s.cards || [];
      if (cards.length) {
        body += '<div class="chip-list">' + cards.map(function (c) {
          return '<span class="chip">' + esc(c) + "</span>";
        }).join("") + "</div>";
      }
      if (!body) return "";
      return '<details class="fold"' + (cards.length || (s.texts || []).length <= 1 ? "" : "") + ">" +
        "<summary>" + esc(s.title) + "</summary>" +
        '<div class="fold-body">' + body + "</div></details>";
    }).join("");
  }

  /* --------------------------------------------------------- 导航高亮 */
  function initNav() {
    var links = Array.prototype.slice.call(document.querySelectorAll(".nav-link"));
    var secs = links.map(function (a) {
      return document.querySelector(a.getAttribute("href"));
    });

    function onScroll() {
      var y = window.scrollY + 120;
      var cur = 0;
      secs.forEach(function (s, i) { if (s && s.offsetTop <= y) cur = i; });
      links.forEach(function (a, i) { a.classList.toggle("active", i === cur); });
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ------------------------------------------------------------------ 启动 */
  function boot() {
    if (!DATA.meta) {
      document.body.insertAdjacentHTML("afterbegin",
        '<div style="background:#ffe9ea;color:#c4121a;padding:14px 20px;font-size:14px;">' +
        "未加载到数据文件 data/data.js，请先运行：<code>python3 scripts/fetch_data.py</code></div>");
      return;
    }
    renderMeta();
    renderProducts();
    renderEventTimeline("event-list", DATA.events, "近 2 个月内暂无进行中 / 即将开始的活动");
    renderShops();
    renderDecks();
    renderRegulation();
    initModal();
    initNav();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
