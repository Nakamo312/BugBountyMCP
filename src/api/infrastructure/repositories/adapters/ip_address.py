"""IP Address repository"""
from api.domain.models import IPAddressModel, ProgramModel
from api.infrastructure.repositories.adapters.sqlalchemy_repository import \
    SQLAlchemyBaseRepository


class SQLAlchemyIPAddressRepository(SQLAlchemyBaseRepository[ProgramModel]):
    """Repository for IPAddress entities"""
    
    model = IPAddressModel
    unique_fields = [("program_id", "address")]
