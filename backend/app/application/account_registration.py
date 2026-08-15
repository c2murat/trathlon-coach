from __future__ import annotations
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.application.athletes import normalize_athlete_display_name
from app.db.models import AthleteProfile, User, UserAthleteMembership
from app.security.identity import normalize_email
from app.security.passwords import hash_password
PUBLIC_ACCOUNT_PLANS=frozenset({"athlete","coach"})
class RegistrationError(ValueError): pass
class AccountRegistrationApplication:
 def __init__(self,session:Session)->None:self._session=session
 def register(self,*,display_name:str,email:str,password:str,account_plan:str,timezone:str)->User:
  if account_plan not in PUBLIC_ACCOUNT_PLANS:raise RegistrationError("invalid_account_plan")
  try:name=normalize_athlete_display_name(display_name)
  except ValueError as error:raise RegistrationError("invalid_display_name") from error
  normalized=normalize_email(email)
  if len(normalized)<3 or len(normalized)>320:raise RegistrationError("invalid_email")
  try:ZoneInfo(timezone)
  except (ZoneInfoNotFoundError,ValueError) as error:raise RegistrationError("invalid_timezone") from error
  if self._session.scalar(select(User.id).where(User.normalized_email==normalized)):raise RegistrationError("registration_unavailable")
  user=User(email=normalized,normalized_email=normalized,auth_subject=f"registered-{uuid4()}",password_hash=hash_password(password),status="active",timezone=timezone,display_name=name,account_plan=account_plan);self._session.add(user);self._session.flush()
  if account_plan=="athlete":
   athlete=AthleteProfile(display_name=name,timezone=timezone,unit_system="metric");membership=UserAthleteMembership(user=user,athlete_profile=athlete,role="athlete",is_active=True,is_default=True);self._session.add_all([athlete,membership]);self._session.flush()
  return user