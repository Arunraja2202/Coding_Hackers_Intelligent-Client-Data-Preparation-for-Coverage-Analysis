import json
from azure.ai.inference import ChatCompletionsClient
from azure.ai.inference.models import SystemMessage, UserMessage
from azure.core.credentials import AzureKeyCredential
from app.config import settings
from app.schemas import TARGET_COLUMNS

SYSTEM_PROMPT="""You are the approved CSI Smart Shipment Data Transformation assistant.
You analyze client shipment workbooks and return a deterministic transformation plan as JSON.
Never invent business data. Never replace missing source values with guesses. Preserve signed returns
and distinguish explicit zero from null/missing. Every output row must be traceable to source rows.
The target structure is Country, Region, Channel, City/State, Category, Brand, SKU, Fact, while
source time periods remain as columns. Detect normal tables, long period tables, wide period tables,
mixed/multi-row headers, matrix layouts, subtotal/Result rows, and multiple unit tabs.
Map only when supported by column names AND sample values. Low-confidence mappings must be null and
listed for review. Return ONLY JSON matching the requested schema."""

PLAN_SCHEMA={
  "dataset_mode":"normal|wide_period|long_period|matrix|unknown",
  "sheet_plans":[{"sheet":"string","header_row":1,"data_start_row":2}],
  "mapping":{"Country":None,"Region":None,"Channel":None,"City/State":None,"Category":None,"Brand":None,"SKU":None,"Fact":None},
  "transformations":[{"rule":"string","columns":[],"reason":"string"}],
  "period_strategy":{"type":"keep_columns|pivot_period_to_columns|parse_existing_period_columns","year_column":None,"period_column":None},
  "matrix_strategy":{"enabled":False,"dimension_rows":[],"value_start_row":None,"unit_row":None,"skip_if_result_in":"B"},
  "confidence":0.0,
  "review":["string"],
  "assumptions":["string"]
}

class CSIClient:
    def __init__(self):
        self.enabled=settings.csi_llm_enabled
        self.endpoint=settings.csi_llm_endpoint
        self.api_key=settings.csi_llm_api_key
        self.model=settings.csi_llm_model
        self.api_version=settings.csi_llm_api_version

    def _call_csi(self, snapshot, required_columns):
        if not self.enabled: raise RuntimeError("CSI LLM is disabled in configuration")
        if not self.api_key or "<YOUR_API_KEY>" in self.api_key:
            raise RuntimeError("CSI LLM API key is not configured. Set CSI_LLM_API_KEY in .env")
        client=ChatCompletionsClient(endpoint=self.endpoint,credential=AzureKeyCredential(self.api_key),api_version=self.api_version)
        user={"target_columns":required_columns,"source_snapshot":snapshot,"required_response_schema":PLAN_SCHEMA}
        response=client.complete(messages=[SystemMessage(content=SYSTEM_PROMPT),UserMessage(content=json.dumps(user,default=str))],model=self.model,headers={"Authorization":self.api_key})
        content=response.choices[0].message.content
        if isinstance(content,list): content="".join(getattr(x,"text",str(x)) for x in content)
        plan=json.loads(content)
        self.validate(plan,required_columns)
        plan["mode"]="CSI_LLM"
        return plan

    def complete_plan(self, snapshot, required_columns):
        """
        Try the approved CSI LLM first (best semantic understanding). If it is
        disabled, misconfigured, unreachable, times out, or returns something
        unparsable, fall back to the local Smart Analyzer heuristic engine so
        the job still completes instead of failing outright. The report always
        records which engine actually produced the plan.
        """
        try:
            return self._call_csi(snapshot, required_columns)
        except Exception as e:
            from . import ai_analyzer
            plan = ai_analyzer.analyze(snapshot, required_columns)
            plan["fallback_reason"] = f"{type(e).__name__}: {e}"
            return plan

    @staticmethod
    def validate(plan,required_columns):
        if not isinstance(plan,dict) or not isinstance(plan.get("mapping"),dict): raise ValueError("CSI returned invalid transformation plan")
        for c in required_columns:
            plan["mapping"].setdefault(c,None)
        try: plan["confidence"]=float(plan.get("confidence",0))
        except: plan["confidence"]=0.0
        plan["review"]=list(plan.get("review",[]))
        return plan
