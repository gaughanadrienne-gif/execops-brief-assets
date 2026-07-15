(function(){
  "use strict";
  var root = document.getElementById("eob-offer");
  if (!root) return;

  var data = null;
  var ROLE_LABEL = {
    cos:"Chief of Staff",
    ea:"Executive Assistant",
    senior_ea:"Senior Executive Assistant",
    ops:"Executive Operations / BizOps"
  };
  var STATUS_CLASS = {
    strong:"eob-g-strong",
    solid:"eob-g-solid",
    below:"eob-g-below",
    wait:"eob-g-wait"
  };
  var TERMS = [
    { id:"eob-oe-t-severance", name:"Severance", why:"what applies if the principal leaves, the role changes, or employment ends." },
    { id:"eob-oe-t-vesting", name:"Vesting schedule and cliff", why:"when the grant vests and what happens during year one.", equityOnly:true },
    { id:"eob-oe-t-review", name:"Refresh grants and review timing", why:"when compensation is reviewed and whether refresh grants are available." },
    { id:"eob-oe-t-title", name:"Title and level clarity", why:"the internal level affects future roles as much as the external title." },
    { id:"eob-oe-t-window", name:"Post-termination exercise window", why:"how long vested private options can be exercised after leaving.", optionsOnly:true },
    { id:"eob-oe-t-change", name:"Change-of-control treatment", why:"what happens to the role, severance, and unvested compensation in a transaction." },
    { id:"eob-oe-t-benefits", name:"Benefits and flexibility", why:"health, retirement, PTO, work mode, and agreed flexibility are documented." }
  ];

  function $(id){ return root.querySelector("#" + id); }
  function money(n){ return "$" + Math.round(n).toLocaleString("en-US"); }
  function parseNum(v){
    var n = parseFloat(String(v).replace(/[^0-9.]/g,""));
    return isNaN(n) ? null : n;
  }
  function amount(id){
    var n = parseNum($(id).value);
    return n == null ? 0 : n;
  }
  function esc(v){
    return String(v == null ? "" : v)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;").replace(/'/g,"&#039;");
  }
  function cite(label,url,detail){
    return '<span class="eob-cite">Source: <a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">'
      + esc(label) + '</a>' + (detail ? " · " + esc(detail) : "") + '</span>';
  }
  function setStatus(el,label,style){
    el.textContent = label;
    el.className = el.className.replace(/eob-g-w+/g,"").trim() + " " + STATUS_CLASS[style];
  }
  function cashGrid(items){
    return '<div class="eob-cash-grid">' + items.map(function(item){
      return '<div class="eob-cash-stat"><span>' + esc(item[0]) + '</span><strong>' + esc(item[1]) + '</strong></div>';
    }).join("") + '</div>';
  }

  function benchmarkFor(role,stage,location){
    var ea = data.executiveAssistant;
    if (role === "cos"){
      var cos = data.chiefOfStaff;
      return {
        kind:"median",
        median:cos.stageMedians[stage],
        label:cos.stageLabels[stage] + " observed median base",
        source:cos.stageSource.source,
        sourceUrl:cos.stageSource.sourceUrl,
        detail:"n=" + cos.stageSource.sample + " overall; stage cell n not published",
        note:"No location or experience multiplier is applied."
      };
    }
    if (role === "ea"){
      if (location !== "national"){
        var geo = ea.geography[location];
        return {
          kind:"band",
          low:geo.cSuiteLow,
          median:geo.cSuiteMedian,
          high:geo.cSuiteHigh,
          label:geo.label + " published executive-support market range",
          source:ea.cSuiteNational.source,
          sourceUrl:ea.cSuiteNational.sourceUrl,
          detail:"self-reported base; geographic cell n not disclosed",
          note:"Published market range, not verified local percentiles."
        };
      }
      return {
        kind:"band",
        low:ea.cSuiteNational.p25,
        median:ea.cSuiteNational.median,
        high:ea.cSuiteNational.p75,
        label:"National EA incumbent middle 50%",
        source:ea.cSuiteNational.source,
        sourceUrl:ea.cSuiteNational.sourceUrl,
        detail:"n≈" + ea.cSuiteNational.sample + " EAs; self-reported base",
        note:"P25 to P75 in a specialized executive-support network."
      };
    }
    if (role === "senior_ea"){
      return {
        kind:"mean",
        median:ea.titleMeans.senior_ea.meanBase,
        label:"Senior EA reported mean base",
        source:ea.independentNational.source,
        sourceUrl:ea.independentNational.sourceUrl,
        detail:"n=" + ea.independentNational.sample + " overall; title cell n not disclosed",
        note:"A contextual mean, not a median or range. No city adjustment is applied."
      };
    }
    var ops = data.executiveOperations.premium;
    return {
      kind:"band",
      low:ops.p25,
      median:ops.median,
      high:ops.p75,
      label:"Premium active Executive Operations postings",
      source:ops.source,
      sourceUrl:ops.sourceUrl,
      detail:"n=" + ops.sample + "; posted midpoint; $100k floor",
      note:"Premium opportunity market, not a national incumbent benchmark."
    };
  }

  function bonusCitation(role){
    if (role === "cos"){
      var c = data.chiefOfStaff.bonusContext;
      return "In a small CoS survey, 56% received a bonus and recipients averaged 19% of base. "
        + cite(c.source,c.sourceUrl,"n=" + c.sample);
    }
    if (role === "ea" || role === "senior_ea"){
      var ea = data.executiveAssistant;
      return "C-Suite Assistants reports 52% discretionary and 16% guaranteed bonus. The independent survey reports an 8.66% average bonus, but its denominator is unclear. "
        + cite(ea.cSuiteNational.source,ea.cSuiteNational.sourceUrl,"n≈" + ea.cSuiteNational.sample + " EAs")
        + " " + cite(ea.independentNational.source,ea.independentNational.sourceUrl,"n=" + ea.independentNational.sample + " overall");
    }
    return "No clean Executive Operations bonus benchmark is available. Treat the target as offer-specific and verify the payout basis and history.";
  }

  function evaluate(){
    var err = $("eob-oe-err");
    err.textContent = "";
    if (!data){
      err.textContent = "Compensation data is still loading. Try again in a moment.";
      return;
    }

    var role = $("eob-oe-role").value;
    var stage = $("eob-oe-stage").value;
    var location = $("eob-oe-tier").value;
    var equity = $("eob-oe-equity").value;
    var base = parseNum($("eob-oe-base").value);
    if (base == null || base <= 0){
      err.textContent = "Enter the annual base salary.";
      $("eob-oe-result").className = $("eob-oe-result").className.replace(" eob-show","");
      return;
    }
    if (base < 1000) base *= 1000;

    var guaranteed = amount("eob-oe-guaranteed");
    var targetPct = amount("eob-oe-bonus");
    var signon = amount("eob-oe-signon");
    var targetBonus = base * targetPct / 100;
    var annualBonusUsed = Math.max(guaranteed,targetBonus);
    var guaranteedFirstYear = base + guaranteed + signon;
    var targetAnnual = base + annualBonusUsed;
    var targetFirstYear = targetAnnual + signon;

    var benchmark = benchmarkFor(role,stage,location);
    var baseStyle,baseLabel,baseText,baseLine;
    if (benchmark.kind === "band"){
      baseLine = benchmark.label + ": " + money(benchmark.low) + " to " + money(benchmark.high) + "; midpoint/median " + money(benchmark.median) + ".";
      if (base < benchmark.low){
        baseStyle = "below";
        baseLabel = "Below observed band";
        baseText = "The offered base is " + money(benchmark.low - base) + " below the bottom of this observed comparison.";
      } else if (base > benchmark.high){
        baseStyle = "strong";
        baseLabel = "Above observed band";
        baseText = "The offered base is above the top of this observed comparison. Confirm that scope, level, and internal title match the pay.";
      } else {
        baseStyle = "solid";
        baseLabel = "Within observed band";
        baseText = "The offered base sits inside this observed comparison. Where it lands should track reporting line, scope, budget, and headcount authority.";
      }
    } else {
      baseLine = benchmark.label + ": " + money(benchmark.median) + ".";
      if (base < benchmark.median){
        baseStyle = "below";
        baseLabel = "Below reported " + benchmark.kind;
        baseText = "The offered base is " + money(benchmark.median - base) + " below the reported " + benchmark.kind + ". This is a reference point, not the bottom of a band.";
      } else {
        baseStyle = "strong";
        baseLabel = "At or above reported " + benchmark.kind;
        baseText = "The offered base is at or above the reported " + benchmark.kind + ". This does not establish that the whole package is competitive.";
      }
    }
    baseText += " " + benchmark.note;

    $("eob-oe-baseband").innerHTML = esc(baseLine) + "<br>" + cite(benchmark.source,benchmark.sourceUrl,benchmark.detail);
    $("eob-oe-basetext").textContent = baseText;
    setStatus($("eob-oe-g-base"),baseLabel,baseStyle);

    $("eob-oe-guaranteedtext").innerHTML = cashGrid([
      ["Base",money(base)],
      ["Guaranteed bonus",money(guaranteed)],
      ["Sign-on",money(signon)],
      ["Guaranteed first year",money(guaranteedFirstYear)]
    ]) + '<p>Guaranteed first-year cash includes the one-time sign-on bonus and does not assign value to target bonus or equity.</p>';
    setStatus($("eob-oe-g-guaranteed"),"Calculated","solid");

    $("eob-oe-targettext").innerHTML = cashGrid([
      ["Target bonus",money(annualBonusUsed)],
      ["Target annual cash",money(targetAnnual)],
      ["Target first year",money(targetFirstYear)]
    ]) + '<p>The target calculation uses the larger of the guaranteed annual minimum and the target percentage, so the same bonus is not counted twice. Sign-on appears only in first-year cash.</p><p>' + bonusCitation(role) + '</p>';
    setStatus($("eob-oe-g-target"),targetPct > 0 ? "Target entered" : (guaranteed > 0 ? "Guaranteed only" : "No bonus entered"),targetPct > 0 || guaranteed > 0 ? "solid" : "wait");

    evaluateEquityAndTerms({
      role:role,
      stage:stage,
      location:location,
      equity:equity,
      base:base,
      guaranteedFirstYear:guaranteedFirstYear,
      targetAnnual:targetAnnual,
      targetPct:targetPct,
      guaranteed:guaranteed,
      benchmark:benchmark,
      baseStyle:baseStyle,
      baseLabel:baseLabel
    });
  }

  function evaluateEquityAndTerms(ctx){
    var shares = amount("eob-oe-shares");
    var fdShares = amount("eob-oe-fdshares");
    var ownership = amount("eob-oe-ownership");
    var strike = amount("eob-oe-strike");
    var common409a = amount("eob-oe-409a");
    var preferred = amount("eob-oe-preferred");
    var grantValue = amount("eob-oe-grantvalue");
    var missingEquity = [];
    var equityReady = false;
    var ownershipCalc = ownership > 0 ? ownership : (shares > 0 && fdShares > 0 ? shares / fdShares * 100 : 0);
    var equityText = "";

    if (ctx.equity === "none"){
      equityText = "No equity is included. This is not automatically below market: 54% held equity in a small CoS survey, while the EA surveys report equity/options for 17% and 23.4% of respondents. Evaluate cash on its own and ask whether equity is available at the internal level.";
      setStatus($("eob-oe-g-equity"),"No equity entered","wait");
    } else if (ctx.equity === "options"){
      if (!(ownershipCalc > 0)) missingEquity.push("Ownership percentage, or both grant shares and fully diluted shares");
      if (!(strike > 0)) missingEquity.push("Strike price");
      if (!(common409a > 0)) missingEquity.push("Latest 409A/common value and date");
      if (!$("eob-oe-t-vesting").checked) missingEquity.push("Vesting schedule and cliff");
      if (!$("eob-oe-t-window").checked) missingEquity.push("Post-termination exercise window");
      equityReady = missingEquity.length === 0;
      equityText = equityReady
        ? "The core inputs needed to discuss this private-option grant are present. Ownership is " + ownershipCalc.toFixed(3) + "%. This still does not make the grant liquid, guaranteed, or comparable with cash."
        : "The grant cannot yet be evaluated responsibly. Treat its value as unknown until the missing items below are supplied.";
      setStatus($("eob-oe-g-equity"),equityReady ? "Enough information" : "Missing information",equityReady ? "strong" : "wait");
    } else if (ctx.equity === "rsu"){
      if (!(grantValue > 0)) missingEquity.push("Stated grant value or a current share-price valuation");
      if (!$("eob-oe-t-vesting").checked) missingEquity.push("Vesting schedule");
      equityReady = missingEquity.length === 0;
      equityText = equityReady
        ? "A stated RSU value and vesting schedule are present. Confirm grant-date units, refresh policy, tax withholding, and what happens if employment ends."
        : "The RSU grant is missing information needed to compare it with the cash package.";
      setStatus($("eob-oe-g-equity"),equityReady ? "Enough information" : "Missing information",equityReady ? "strong" : "wait");
    } else {
      if (!(grantValue > 0 || ownershipCalc > 0)) missingEquity.push("A stated grant value or computable ownership percentage");
      if (!$("eob-oe-t-vesting").checked) missingEquity.push("Vesting schedule and cliff");
      equityReady = missingEquity.length === 0;
      equityText = equityReady ? "Basic grant information is present, but the security type and valuation rules still need confirmation." : "The security type or valuation information is incomplete.";
      setStatus($("eob-oe-g-equity"),equityReady ? "Partial information" : "Missing information",equityReady ? "solid" : "wait");
    }
    $("eob-oe-equitytext").textContent = equityText;
    var eqList = $("eob-oe-equitylist");
    eqList.innerHTML = "";
    missingEquity.forEach(function(item){
      var li = document.createElement("li");
      li.textContent = item;
      eqList.appendChild(li);
    });

    var scenarios = "";
    if (ctx.equity === "options" && shares > 0 && strike > 0 && common409a > 0){
      var commonSpread = Math.max(common409a - strike,0) * shares;
      scenarios = '<div class="eob-scenarios">'
        + '<div class="eob-scenario"><span>Zero-value case</span><strong>$0</strong></div>'
        + '<div class="eob-scenario"><span>409A spread</span><strong>' + money(commonSpread) + '</strong></div>';
      if (preferred > 0){
        scenarios += '<div class="eob-scenario"><span>Preferred-price spread</span><strong>' + money(Math.max(preferred - strike,0) * shares) + '</strong></div>';
      }
      scenarios += '</div><p class="eob-cite">Illustrative total-grant spread before vesting, taxes, exercise cost, dilution, preferences, and liquidity risk. Preferred price is not common-share cash value.</p>';
    }
    var equityCitation = "";
    if (ctx.role === "cos"){
      var cosEquity = data.chiefOfStaff.equityContext;
      equityCitation = '<p class="eob-cite">Incidence context: 54% held equity in this small survey. '
        + cite(cosEquity.source,cosEquity.sourceUrl,"n=" + cosEquity.sample) + '</p>';
    } else if (ctx.role === "ea" || ctx.role === "senior_ea"){
      var eaEquity = data.executiveAssistant;
      equityCitation = '<p class="eob-cite">Incidence context: 17% in C-Suite Assistants and 23.4% in the independent survey. '
        + cite(eaEquity.cSuiteNational.source,eaEquity.cSuiteNational.sourceUrl,"n≈" + eaEquity.cSuiteNational.sample + " EAs")
        + " " + cite(eaEquity.independentNational.source,eaEquity.independentNational.sourceUrl,"n=" + eaEquity.independentNational.sample + " overall") + '</p>';
    } else {
      equityCitation = '<p class="eob-cite">No role-specific Executive Operations equity band is used. Review the inputs with the <a href="https://carta.com/learn/equity/startup-equity-calculator/" target="_blank" rel="noopener noreferrer">Carta equity guide</a>.</p>';
    }
    $("eob-oe-scenarios").innerHTML = scenarios + equityCitation;
    renderTermsAndSummary(ctx,missingEquity,equityReady);
  }

  function renderTermsAndSummary(ctx,missingEquity,equityReady){
    var relevantTerms = TERMS.filter(function(t){
      if (t.optionsOnly && ctx.equity !== "options") return false;
      if (t.equityOnly && ctx.equity === "none") return false;
      return true;
    });
    var missingTerms = relevantTerms.filter(function(t){ return !$(t.id).checked; });
    var coveredCount = relevantTerms.length - missingTerms.length;
    var halfway = Math.ceil(relevantTerms.length / 2);
    setStatus(
      $("eob-oe-g-terms"),
      missingTerms.length === 0 ? "Complete" : (coveredCount >= halfway ? "Open items" : "Several open items"),
      missingTerms.length === 0 ? "strong" : (coveredCount >= halfway ? "solid" : "below")
    );
    $("eob-oe-termstext").textContent = "The offer addresses " + coveredCount + " of " + relevantTerms.length + " relevant terms.";
    var termsList = $("eob-oe-termslist");
    termsList.innerHTML = "";
    missingTerms.forEach(function(t){
      var li = document.createElement("li");
      li.textContent = t.name + ": " + t.why;
      termsList.appendChild(li);
    });

    var qs = [];
    missingEquity.forEach(function(item){
      if (qs.length < 2) qs.push("Can you provide: " + item.toLowerCase() + "?");
    });
    if (ctx.baseStyle === "below"){
      var target = ctx.benchmark.kind === "band" ? ctx.benchmark.low : ctx.benchmark.median;
      qs.push("Is there room to move base closer to " + money(target) + ", the named reference point, and if not, where is there flexibility?");
    }
    if (ctx.targetPct === 0 && ctx.guaranteed === 0) qs.push("Is an annual bonus available at this internal level, and what determines payout?");
    else qs.push("Is the annual bonus discretionary or formula-based, and what has it paid historically?");
    if (!$("eob-oe-t-severance").checked) qs.push("What severance applies if the principal leaves, the role changes, or employment ends?");
    if (!$("eob-oe-t-review").checked) qs.push("When is the first compensation review, and are refresh grants available?");
    if (!$("eob-oe-t-title").checked) qs.push("What internal level does this role map to?");
    if (qs.length < 3) qs.push("What does success look like in the first year, and what scope do I own outright?");
    qs = qs.slice(0,4);
    var qList = $("eob-oe-questions");
    qList.innerHTML = "";
    qs.forEach(function(q){
      var li = document.createElement("li");
      li.textContent = q;
      qList.appendChild(li);
    });

    var summary = ROLE_LABEL[ctx.role];
    if (ctx.role === "cos") summary += ", " + data.chiefOfStaff.stageLabels[ctx.stage];
    else if ((ctx.role === "ea" || ctx.role === "senior_ea") && ctx.location !== "national") summary += ", " + data.executiveAssistant.geography[ctx.location].label;
    $("eob-oe-summary").textContent = summary;
    $("eob-oe-overall").textContent = "This readout keeps the components separate: base is " + ctx.baseLabel.toLowerCase()
      + "; guaranteed first-year cash is " + money(ctx.guaranteedFirstYear)
      + "; target annual cash is " + money(ctx.targetAnnual)
      + "; and equity information is " + (ctx.equity === "none" ? "not included" : (equityReady ? "sufficient for a first-pass discussion" : "incomplete")) + ".";
    setStatus($("eob-oe-verdict"),"Component readout","solid");

    var panel = $("eob-oe-result");
    if (panel.className.indexOf("eob-show") === -1) panel.className += " eob-show";
    setTimeout(postHeight,60);
  }

  function updateConditionalFields(){
    var role = $("eob-oe-role").value;
    $("eob-oe-stage-wrap").classList.toggle("eob-hidden",role !== "cos");
    $("eob-oe-location-wrap").classList.toggle("eob-hidden",!(role === "ea" || role === "senior_ea"));
    $("eob-oe-equity-fields").classList.toggle("eob-hidden",$("eob-oe-equity").value === "none");
    setTimeout(postHeight,60);
  }

  function postHeight(){
    var h = root.scrollHeight;
    if (window.parent && window.parent !== window){
      window.parent.postMessage({type:"eob-offer-height",height:h},"*");
    }
  }

  $("eob-oe-go").addEventListener("click",evaluate);
  $("eob-oe-role").addEventListener("change",updateConditionalFields);
  $("eob-oe-equity").addEventListener("change",updateConditionalFields);
  updateConditionalFields();

  fetch("compensation-data.json",{cache:"no-store"})
    .then(function(response){
      if (!response.ok) throw new Error("Data request failed");
      return response.json();
    })
    .then(function(payload){
      data = payload;
      $("eob-oe-go").disabled = false;
      $("eob-oe-go").textContent = "Evaluate this offer";
      $("eob-oe-data-version").textContent = "Compensation data version: " + data.updatedLabel + ".";
      postHeight();
    })
    .catch(function(){
      $("eob-oe-go").textContent = "Compensation data unavailable";
      $("eob-oe-err").textContent = "The benchmark file could not load. Refresh the page before evaluating an offer.";
      $("eob-oe-data-version").textContent = "Compensation data file unavailable.";
      postHeight();
    });

  if (window.ResizeObserver) new ResizeObserver(postHeight).observe(root);
  window.addEventListener("load",postHeight);
  window.addEventListener("resize",postHeight);
  root.addEventListener("change",function(){ setTimeout(postHeight,60); });

  var subForm = root.querySelector("#eob-subscribe");
  var subMsg = root.querySelector("#eob-sub-msg");
  if (subForm){
    var frame = document.createElement("iframe");
    frame.name = "eob-ml-frame";
    frame.style.display = "none";
    frame.setAttribute("aria-hidden","true");
    root.appendChild(frame);
    subForm.addEventListener("submit",function(){
      var btn = subForm.querySelector("button");
      if (btn){ btn.disabled = true; btn.textContent = "Sending..."; }
      setTimeout(function(){
        if (subMsg) subMsg.textContent = "You are in. Check your inbox for the next note.";
        subForm.reset();
        if (btn){ btn.disabled = false; btn.textContent = "Subscribe"; }
        postHeight();
      },900);
    });
  }
})();
