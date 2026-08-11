from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from sqlalchemy import create_engine,inspect,text
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from app.core.settings import get_settings

CHECKS={
"athletes_without_active_owner":"SELECT count(*) FROM athlete_profiles a WHERE NOT EXISTS (SELECT 1 FROM user_athlete_memberships m WHERE m.athlete_profile_id=a.id AND m.role='owner' AND m.is_active IS TRUE)",
"legacy_owner_membership_missing":"SELECT count(*) FROM athlete_profiles a WHERE NOT EXISTS (SELECT 1 FROM user_athlete_memberships m WHERE m.athlete_profile_id=a.id AND m.user_id=a.user_id AND m.role='owner' AND m.is_active IS TRUE)",
"legacy_owner_mismatch":"SELECT count(*) FROM athlete_profiles a JOIN user_athlete_memberships m ON m.athlete_profile_id=a.id AND m.role='owner' AND m.is_active IS TRUE WHERE m.user_id<>a.user_id",
"multiple_active_defaults":"SELECT count(*) FROM (SELECT user_id FROM user_athlete_memberships WHERE is_active IS TRUE AND is_default IS TRUE GROUP BY user_id HAVING count(*)>1) q",
"inactive_defaults":"SELECT count(*) FROM user_athlete_memberships WHERE is_active IS FALSE AND is_default IS TRUE",
"deleted_athlete_defaults":"SELECT count(*) FROM user_athlete_memberships m JOIN athlete_profiles a ON a.id=m.athlete_profile_id WHERE m.is_default IS TRUE AND a.deleted_at IS NOT NULL",
"active_memberships_deleted_athlete":"SELECT count(*) FROM user_athlete_memberships m JOIN athlete_profiles a ON a.id=m.athlete_profile_id WHERE m.is_active IS TRUE AND a.deleted_at IS NOT NULL",
}
BASELINE={"users":"SELECT count(*) FROM users","athlete_profiles":"SELECT count(*) FROM athlete_profiles","memberships":"SELECT count(*) FROM user_athlete_memberships","owner_memberships":"SELECT count(*) FROM user_athlete_memberships WHERE role='owner'","active_memberships":"SELECT count(*) FROM user_athlete_memberships WHERE is_active IS TRUE","active_defaults":"SELECT count(*) FROM user_athlete_memberships WHERE is_active IS TRUE AND is_default IS TRUE","deleted_athletes":"SELECT count(*) FROM athlete_profiles WHERE deleted_at IS NOT NULL","integration_accounts":"SELECT count(*) FROM integration_accounts","strava_accounts":"SELECT count(*) FROM integration_accounts WHERE provider='strava'"}
def run(connection):
 columns={c['name'] for c in inspect(connection).get_columns('athlete_profiles')}; schema='0017' if 'user_id' in columns else '0018'
 baseline={k:connection.scalar(text(q)) for k,q in BASELINE.items()}; issues={}
 if schema=='0017': issues={k:connection.scalar(text(q)) for k,q in CHECKS.items()}
 else:
  post={"athletes_without_active_owner":CHECKS["athletes_without_active_owner"],"multiple_active_defaults":CHECKS["multiple_active_defaults"],"inactive_defaults":CHECKS["inactive_defaults"],"deleted_athlete_defaults":CHECKS["deleted_athlete_defaults"],"active_memberships_deleted_athlete":CHECKS["active_memberships_deleted_athlete"],"invalid_display_names":"SELECT count(*) FROM athlete_profiles WHERE display_name IS NULL OR char_length(btrim(display_name)) NOT BETWEEN 1 AND 200"}; issues={k:connection.scalar(text(q)) for k,q in post.items()}
 return {"schema":schema,"baseline":baseline,"checks":issues,"issue_count":sum(issues.values())}
def main(argv=None):
 p=argparse.ArgumentParser();p.add_argument('--format',choices=('text','json'),default='text');p.add_argument('--all-athletes',action='store_true');a=p.parse_args(argv)
 engine=create_engine(get_settings().database_url,pool_pre_ping=True)
 with engine.connect() as c: result=run(c);c.rollback()
 print(json.dumps(result,sort_keys=True,separators=(',',':')) if a.format=='json' else json.dumps(result,indent=2,sort_keys=True));return 1 if result['issue_count'] else 0
if __name__=='__main__': raise SystemExit(main())
