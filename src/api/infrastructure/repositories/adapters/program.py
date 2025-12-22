"""Program repository"""
from api.domain.models import ProgramModel
from sqlalchemy_repository import SQLAlchemyBaseRepository



class SQLAlchemyProgramRepository(SQLAlchemyBaseRepository[ProgramModel]):
    """Repository for Program entities"""
    
    model = ProgramModel
    unique_fields = [("name",)]
