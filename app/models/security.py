"""
Modelos ORM — Módulo de Seguridad, cPanel y RBAC.

Tablas: roles, modulos, permisos, rol_permisos, usuarios,
        sesiones_usuario, bitacora_auditoria
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Role(Base):
    """Tabla: roles"""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)

    # Relaciones
    usuarios: Mapped[List["Usuario"]] = relationship(back_populates="rol")
    rol_permisos: Mapped[List["RolPermiso"]] = relationship(
        back_populates="rol", cascade="all, delete-orphan"
    )


class Modulo(Base):
    """Tabla: modulos"""

    __tablename__ = "modulos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)

    # Relaciones
    rol_permisos: Mapped[List["RolPermiso"]] = relationship(
        back_populates="modulo", cascade="all, delete-orphan"
    )


class Permiso(Base):
    """Tabla: permisos"""

    __tablename__ = "permisos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    accion: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)

    # Relaciones
    rol_permisos: Mapped[List["RolPermiso"]] = relationship(
        back_populates="permiso", cascade="all, delete-orphan"
    )


class RolPermiso(Base):
    """Tabla: rol_permisos (PK compuesta)"""

    __tablename__ = "rol_permisos"
    __table_args__ = (
        UniqueConstraint("rol_id", "modulo_id", "permiso_id", name="uq_rol_permiso"),
    )

    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    modulo_id: Mapped[int] = mapped_column(ForeignKey("modulos.id"), primary_key=True)
    permiso_id: Mapped[int] = mapped_column(ForeignKey("permisos.id"), primary_key=True)

    # Relaciones
    rol: Mapped["Role"] = relationship(back_populates="rol_permisos")
    modulo: Mapped["Modulo"] = relationship(back_populates="rol_permisos")
    permiso: Mapped["Permiso"] = relationship(back_populates="rol_permisos")


class Usuario(Base):
    """Tabla: usuarios"""

    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre_completo: Mapped[str] = mapped_column(String(120), nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    rol_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    es_superuser: Mapped[bool] = mapped_column(Boolean, default=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relaciones
    rol: Mapped["Role"] = relationship(back_populates="usuarios")
    sesiones: Mapped[List["SesionUsuario"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )
    sesiones_caja: Mapped[List["SesionCaja"]] = relationship(
        back_populates="usuario", cascade="all, delete-orphan"
    )
    bitacora: Mapped[List["BitacoraAuditoria"]] = relationship(back_populates="usuario")
    facturas: Mapped[List["Factura"]] = relationship(back_populates="usuario")
    compras: Mapped[List["Compra"]] = relationship(back_populates="usuario")
    cierres_z: Mapped[List["CierreZ"]] = relationship(back_populates="usuario")


class SesionUsuario(Base):
    """Tabla: sesiones_usuario"""

    __tablename__ = "sesiones_usuario"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    usuario_id: Mapped[int] = mapped_column(
        ForeignKey("usuarios.id"), nullable=False
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    fecha_inicio: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    fecha_expiracion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    activa: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relaciones
    usuario: Mapped["Usuario"] = relationship(back_populates="sesiones")


class BitacoraAuditoria(Base):
    """Tabla: bitacora_auditoria"""

    __tablename__ = "bitacora_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("usuarios.id"), nullable=True
    )
    accion: Mapped[str] = mapped_column(String(100), nullable=False)
    modulo: Mapped[str] = mapped_column(String(100), nullable=False)
    detalles: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    fecha: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    # Relaciones
    usuario: Mapped[Optional["Usuario"]] = relationship(back_populates="bitacora")