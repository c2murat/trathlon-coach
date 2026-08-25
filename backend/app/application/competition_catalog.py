from app.core.settings import Settings
from app.domains.competition_catalog.models import CatalogError,CatalogProviderInfo,CatalogSearch
from app.integrations.competition_catalog import AIWebCompetitionProvider,TavilyCompetitionProvider,WorldTriathlonProvider
class CompetitionCatalogRegistry:
 def __init__(self,providers):self.providers={x.name:x for x in providers}
 def infos(self):return [CatalogProviderInfo(provider=x.name,label=x.label,configured=x.configured,supported_categories=list(x.supported_categories),search_mode=getattr(x,"search_mode","structured"),supports_structured_detail=getattr(x,"supports_structured_detail",True),supports_structured_import=getattr(x,"supports_structured_import",True),supports_search_to_manual_goal=getattr(x,"supports_search_to_manual_goal",False)) for x in self.providers.values()]
 def provider(self,name):
  value=self.providers.get(name)
  if value is None:raise CatalogError("provider_unknown")
  return value
 def search(self,query,provider=None):
  selected=[self.provider(provider)] if provider else [x for x in self.providers.values() if x.configured and getattr(x,"search_mode","structured")=="structured"]
  if not selected:raise CatalogError("provider_not_configured")
  result=[]
  for item in selected:result.extend(item.search(query))
  return sorted(result,key=lambda x:(x.start_date,x.name))[:query.limit]
 def web_search(self,query,provider,phase):
  selected=self.provider(provider)
  if getattr(selected,"search_mode","structured")!="web":raise CatalogError("provider_search_mode_invalid")
  return selected.search_web(query,phase)
def build_catalog_registry(settings:Settings):
 return CompetitionCatalogRegistry([
  WorldTriathlonProvider(settings.world_triathlon_api_key.get_secret_value() if settings.world_triathlon_enabled and settings.world_triathlon_api_key else None,settings.world_triathlon_api_base_url,settings.competition_catalog_timeout_seconds),
  AIWebCompetitionProvider(settings.openai_api_key.get_secret_value() if settings.ai_web_competition_enabled and settings.openai_api_key else None,settings.ai_web_competition_model,settings.ai_web_competition_timeout_seconds,settings.ai_web_competition_max_results),
  TavilyCompetitionProvider(settings.tavily_api_key.get_secret_value() if settings.tavily_competition_enabled and settings.tavily_api_key else None,settings.tavily_competition_search_depth,settings.tavily_competition_timeout_seconds,settings.tavily_competition_max_results,settings.tavily_competition_use_extract),
 ])
