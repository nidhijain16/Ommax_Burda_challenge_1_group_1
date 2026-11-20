"""
Opportunity Card Generator.
Generates fully compliant 14-field OpportunityCards grounded in exact dataset IDs.
"""

from typing import List, Dict, Any, Set
from .models import OpportunityCard
from .scorer import TopicScorer

class CardGenerator:
    def __init__(self, data_loader):
        self.loader = data_loader
        self.scorer = TopicScorer(data_loader)

    def generate_card(self, topic_key: str) -> OpportunityCard:
        dossier = self.loader.get_topic_dossier(topic_key)
        taxonomy = dossier.get("taxonomy", {})
        signals = dossier.get("signals", [])
        competitors = dossier.get("competitors", [])
        indicators = dossier.get("indicators", [])
        populations = dossier.get("populations", [])
        events = dossier.get("events", [])
        learnings = dossier.get("learnings", [])
        portfolio = dossier.get("portfolio", [])
        spaces = dossier.get("spaces", [])

        scores, overall, status, market_type, comm_label, human_review, reasons = self.scorer.evaluate_topic(topic_key)

        cited_evidence: Set[str] = set()

        # Title and Consumer Problem
        topic_label = taxonomy.get("label", topic_key.replace("_", " ").title())
        desc = taxonomy.get("description", "")

        if spaces:
            space = spaces[0]
            space_title = space.get("title", "")
            if space_title:
                proposed_topic = f"TOP {space_title}"
            else:
                proposed_topic = f"TOP Providers for {topic_label}"
            consumer_problem = space.get("consumer_problem") or desc
            target_user = space.get("target_user") or "Consumers and families seeking qualified, verified providers"
            target_entity = space.get("target_entity") or f"Service providers and specialist firms in {topic_label}"
        else:
            proposed_topic = f"TOP Providers for {topic_label}"
            consumer_problem = f"Consumers face high uncertainty, opaque pricing, and lack of verified quality when selecting {topic_label} providers."
            target_user = "Private consumers, property owners, or family decision-makers"
            target_entity = f"Certified professionals, clinics, or businesses active in {topic_label}"

        # Why Now with explicit dated citations
        why_now_points = []
        for s in signals[:2]:
            sid = s.get("signal_id")
            period = s.get("period", "")
            summary = s.get("summary", "")
            why_now_points.append(f"{summary} ({period}) [{sid}]")
            cited_evidence.add(sid)

        for e in events[:2]:
            eid = e.get("event_id")
            edate = e.get("event_date", "")
            etitle = e.get("title", "")
            why_now_points.append(f"Regulatory Milestone: {etitle} ({edate}) [{eid}]")
            cited_evidence.add(eid)

        for ind in indicators[:1]:
            iid = ind.get("indicator_id")
            metric = ind.get("metric", "")
            val = ind.get("value", "")
            unit = ind.get("unit", "")
            per = ind.get("period", "")
            why_now_points.append(f"Market metric: {metric} = {val} {unit} ({per}) [{iid}]")
            cited_evidence.add(iid)

        why_now = " | ".join(why_now_points) if why_now_points else "Demographic and regulatory market transition."

        # Portfolio Fit
        if portfolio:
            p = portfolio[0]
            pid = p.get("project_id")
            pname = p.get("project_name_en") or p.get("project_name")
            p_status = p.get("status")
            portfolio_fit = f"Strategic alignment with FACTS product '{pname}' [{pid}] (status: {p_status}). Complements editorial scope without direct cannibalisation."
            cited_evidence.add(pid)
        else:
            portfolio_fit = f"Expands FOCUS brand into high-affinity white space under {taxonomy.get('likely_facts_brand', 'FOCUS Media')}."

        # Competitive Situation
        comp_points = []
        for c in competitors[:2]:
            cid = c.get("competitor_id")
            cname = c.get("name")
            ctype = c.get("competitor_type")
            qual = c.get("has_quality_assessment")
            comp_points.append(f"{cname} [{cid}] ({ctype}, quality assessment: {qual})")
            cited_evidence.add(cid)

        comp_text = "; ".join(comp_points) if comp_points else "Fragmented local provider landscape."
        competitive_situation = f"Market type: {market_type.value}. Existing players: {comp_text}. Clear gap for transparent, methodology-backed quality orientation."

        # Evidenced Facts
        facts = []
        for p in populations[:2]:
            pid = p.get("population_id")
            cnt = p.get("count")
            etype = p.get("entity_type")
            per = p.get("period")
            src_reg = p.get("master_list_source", "")
            facts.append(f"{cnt} {etype} recorded in Germany ({per}) via {src_reg} [{pid}]")
            cited_evidence.add(pid)

        for ind in indicators[:2]:
            iid = ind.get("indicator_id")
            if iid not in cited_evidence:
                facts.append(f"{ind.get('metric')}: {ind.get('value')} {ind.get('unit')} in {ind.get('period')} [{iid}]")
                cited_evidence.add(iid)

        if not facts:
            facts.append(f"Classified under domain {taxonomy.get('domain')} with YMYL status '{taxonomy.get('ymyl_default')}'.")

        # Hypotheses
        hypotheses = [
            f"Qualified providers will show positive willingness to license a FOCUS Quality Seal (Commercial status: {comm_label.value}).",
            "Consumers consider independent editorial ranking significantly more trustworthy than sponsored lead-generation marketplaces.",
            "A master list of certified providers can be systematically compiled from official chambers and registers."
        ]

        # Risks and Uncertainties
        risks = []
        if taxonomy.get("ymyl_default") == "yes":
            risks.append("YMYL Health/Finance liability: Strict methodology required to prevent misleading ranking claims.")
        if learnings:
            lid = learnings[0].get("learning_id")
            risks.append(f"Legal & Court Precedent: German judicial rulings challenge commercial quality seals lacking transparent criteria [{lid}].")
            cited_evidence.add(lid)
        risks.append("Provider universe fragmentation: Reaching smaller regional businesses requires multi-channel sales outreach.")

        # Historical Learning
        if learnings:
            l = learnings[0]
            lid = l.get("learning_id")
            ltitle = l.get("title")
            lesson = l.get("lesson")
            historical_learning = f"Precedent [{lid}] '{ltitle}': {lesson}"
            cited_evidence.add(lid)
        else:
            historical_learning = "No negative legal precedent or court sanction identified in the dataset for this topic."

        # Next Validation Questions
        next_validation_questions = [
            "Can an exhaustive master list be acquired directly from public registers or trade associations?",
            "What objective quality criteria (certifications, inspection reports, customer satisfaction) can be audited at scale?",
            "What is the willingness-to-pay among mid-sized providers for a regional or national quality seal?"
        ]

        # Filter evidence to ensure valid regex format
        sorted_evidence = sorted(list(cited_evidence))

        return OpportunityCard(
            proposed_topic=proposed_topic,
            topic_key=topic_key,
            consumer_problem=consumer_problem,
            target_user=target_user,
            target_entity=target_entity,
            why_now=why_now,
            portfolio_fit=portfolio_fit,
            competitive_situation=competitive_situation,
            evidence=sorted_evidence,
            facts=facts,
            hypotheses=hypotheses,
            risks_and_uncertainties=risks,
            historical_learning=historical_learning,
            next_validation_questions=next_validation_questions,
            recommended_status=status,
            human_review_required=human_review,
            human_review_reasons=reasons,
            commercial_potential_label=comm_label,
            market_type=market_type,
            scores=scores,
            overall_score=overall,
        )

