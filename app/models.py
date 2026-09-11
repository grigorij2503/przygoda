from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from app.database import Base

class GameSession(Base):
    __tablename__ = "game_sessions"

    id = Column(Integer, primary_key=True, index=True)
    room_code = Column(String(50), unique=True, index=True, nullable=False)
    title = Column(String(200), default="Wyprawa do Przeklętej Twierdzy")
    setting_theme = Column(String(100), default="Dark Fantasy / Gothic Horror")
    campaign_intro = Column(Text, default="")
    current_turn_number = Column(Integer, default=1)
    is_turn_resolving = Column(Boolean, default=False)
    status = Column(String(50), default="in_progress")  # "lobby", "in_progress"
    active_boss_name = Column(String(100), nullable=True)
    active_boss_title = Column(String(150), nullable=True)
    active_boss_hp = Column(Integer, nullable=True)
    active_boss_max_hp = Column(Integer, nullable=True)
    active_boss_armor = Column(Integer, nullable=False, default=0)
    active_boss_defense_dc = Column(Integer, nullable=False, default=12)
    active_boss_phase = Column(Integer, nullable=False, default=1)
    active_boss_effects = Column(JSON, default=list)
    active_boss_features = Column(JSON, default=list)
    active_boss_telegraph = Column(JSON, nullable=True)

    pending_naming_category = Column(String(50), nullable=True)  # boss, location, weapon, attack
    pending_naming_prompt = Column(Text, nullable=True)
    pending_naming_character_id = Column(Integer, nullable=True)
    pending_naming_character_name = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    characters = relationship("Character", back_populates="session", cascade="all, delete-orphan")
    turns = relationship("Turn", back_populates="session", cascade="all, delete-orphan")
    lore_entities = relationship("NamedLoreEntity", back_populates="session", cascade="all, delete-orphan")


class Character(Base):
    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False)
    player_name = Column(String(100), nullable=False)
    name = Column(String(100), nullable=False)
    character_class = Column(String(100), default="Wojownik")
    level = Column(Integer, default=1)
    xp = Column(Integer, default=0)
    current_hp = Column(Integer, default=25)
    max_hp = Column(Integer, default=25)
    strength = Column(Integer, default=2)
    agility = Column(Integer, default=1)
    intellect = Column(Integer, default=1)
    charisma = Column(Integer, default=0)
    unspent_stat_points = Column(Integer, nullable=False, default=0)
    personal_note = Column(Text, nullable=False, default="")
    status_effects = Column(JSON, default=list)
    is_alive = Column(Boolean, default=True)
    is_ready = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("GameSession", back_populates="characters")
    inventory = relationship("InventoryItem", back_populates="character", cascade="all, delete-orphan")
    actions = relationship("PlayerAction", back_populates="character", cascade="all, delete-orphan")


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(Integer, primary_key=True, index=True)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    description = Column(String(300), default="")
    item_type = Column(String(50), default="weapon")  # weapon, shield, armor, accessory, consumable, misc
    target_stat = Column(String(50), default="strength")  # strength, agility, intellect, charisma, hp_max, none
    stat_bonus = Column(Integer, default=0)
    damage_power = Column(Integer, nullable=False, default=0)
    hands_required = Column(Integer, nullable=False, default=1)  # 1 albo 2 dla broni; pozostałe typy ignorują tę wartość
    is_equipped = Column(Boolean, default=False)
    quantity = Column(Integer, default=1)

    character = relationship("Character", back_populates="inventory")


class Turn(Base):
    __tablename__ = "turns"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False)
    turn_number = Column(Integer, nullable=False)
    status = Column(String(50), default="waiting_for_actions")  # waiting_for_actions, resolving, completed
    gm_narration = Column(Text, default="")
    next_turn_prompt = Column(Text, default="")
    suggested_actions = Column(JSON, default=list)
    image_prompt = Column(Text, default="")
    image_url = Column(String(500), nullable=True)
    is_generating_image = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = Column(DateTime, nullable=True)
    mechanics_resolved_at = Column(DateTime, nullable=True)
    combat_events = Column(JSON, default=list)

    session = relationship("GameSession", back_populates="turns")
    actions = relationship("PlayerAction", back_populates="turn", cascade="all, delete-orphan")


class PlayerAction(Base):
    __tablename__ = "player_actions"

    id = Column(Integer, primary_key=True, index=True)
    turn_id = Column(Integer, ForeignKey("turns.id", ondelete="CASCADE"), nullable=False)
    character_id = Column(Integer, ForeignKey("characters.id", ondelete="CASCADE"), nullable=False)
    action_text = Column(Text, nullable=False)
    intent = Column(String(30), nullable=True, default=None)
    target_ref = Column(String(100), nullable=True, default=None)
    tested_stat = Column(String(50), nullable=True, default=None)
    dice_roll_raw = Column(Integer, nullable=True, default=None)
    stat_modifier = Column(Integer, nullable=True, default=None)
    item_modifier = Column(Integer, nullable=True, default=None)
    status_modifier = Column(Integer, nullable=False, default=0)
    dice_total = Column(Integer, nullable=True, default=None)
    dc = Column(Integer, nullable=True, default=None)
    outcome_tier = Column(String(50), nullable=True, default=None)  # critical_success, success, partial_success, failure, critical_failure
    gm_individual_summary = Column(Text, default="")
    damage_dealt = Column(Integer, nullable=False, default=0)
    damage_roll = Column(Integer, nullable=False, default=0)
    damage_base = Column(Integer, nullable=False, default=0)
    damage_reduction = Column(Integer, nullable=False, default=0)
    hp_delta = Column(Integer, nullable=False, default=0)
    xp_gained = Column(Integer, nullable=False, default=0)
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    turn = relationship("Turn", back_populates="actions")
    character = relationship("Character", back_populates="actions")


class NamedLoreEntity(Base):
    __tablename__ = "named_lore_entities"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False)
    category = Column(String(50), nullable=False)  # boss, location, weapon, attack
    original_description = Column(Text, nullable=False)
    custom_name = Column(String(150), nullable=False)
    named_by_character_id = Column(Integer, nullable=True)
    named_by_character_name = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    session = relationship("GameSession", back_populates="lore_entities")
