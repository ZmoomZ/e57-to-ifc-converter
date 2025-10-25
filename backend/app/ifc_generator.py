import ifcopenshell
import ifcopenshell.api
from datetime import datetime
from typing import Dict, List, Any
import json

class IFCGenerator:
    """
    Генератор IFC4 файлов из сегментированной модели
    """
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.model_path = f"models/{task_id}.json"
        self.ifc_file = None
        self.project = None
        self.site = None
        self.building = None
        self.storey = None
        
    def load_model_data(self) -> Dict[str, Any]:
        """
        Загрузка данных модели из JSON
        """
        with open(self.model_path, 'r') as f:
            return json.load(f)
    
    def create_ifc_structure(self):
        """
        Создание базовой структуры IFC файла
        """
        # Создаем новый IFC4 файл
        self.ifc_file = ifcopenshell.file(schema="IFC4")
        
        # Создаем Project
        self.project = ifcopenshell.api.run("root.create_entity", self.ifc_file, 
            ifc_class="IfcProject",
            name="E57 to IFC Conversion"
        )
        
        # Устанавливаем единицы измерения (метры)
        ifcopenshell.api.run("unit.assign_unit", self.ifc_file)
        
        # Создаем контекст геометрии
        context = ifcopenshell.api.run("context.add_context", self.ifc_file, 
            context_type="Model"
        )
        
        body = ifcopenshell.api.run("context.add_context", self.ifc_file,
            context_type="Model", 
            context_identifier="Body",
            target_view="MODEL_VIEW", 
            parent=context
        )
        
        # Создаем Site
        self.site = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcSite",
            name="Site"
        )
        ifcopenshell.api.run("aggregate.assign_object", self.ifc_file,
            relating_object=self.project, 
            products=[self.site]
        )
        
        # Создаем Building
        self.building = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcBuilding",
            name="Building"
        )
        ifcopenshell.api.run("aggregate.assign_object", self.ifc_file,
            relating_object=self.site, 
            products=[self.building]
        )
        
        # Создаем Storey (этаж)
        self.storey = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcBuildingStorey",
            name="Ground Floor"
        )
        ifcopenshell.api.run("aggregate.assign_object", self.ifc_file,
            relating_object=self.building, 
            products=[self.storey]
        )
        
        print("IFC структура создана")
    
    def create_slab(self, slab_data: Dict[str, Any]):
        """
        Создание плиты (IfcSlab)
        """
        slab = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcSlab",
            name=f"Slab at Z={slab_data['z']:.2f}"
        )
        
        # Простая прямоугольная геометрия (для MVP)
        # TODO: использовать реальные контуры из сегментации
        
        ifcopenshell.api.run("spatial.assign_container", self.ifc_file,
            relating_structure=self.storey,
            products=[slab]
        )
        
        return slab
    
    def create_wall(self, wall_data: Dict[str, Any]):
        """
        Создание стены (IfcWall) с геометрией
        """
        wall = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcWall",
            name="Wall"
        )
        
        # Создаем простую геометрию стены (экструдированный прямоугольник)
        start = wall_data['start']
        end = wall_data['end']
        height = wall_data['height']
        thickness = wall_data['thickness']
        
        # Вычисляем длину и направление стены
        import math
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.sqrt(dx**2 + dy**2)
        
        if length < 0.1:  # Слишком короткая стена
            return None
        
        # Создаем представление (representation)
        context = self.ifc_file.by_type("IfcGeometricRepresentationSubContext")[0]
        
        # Создаем простой прямоугольный профиль
        rectangle = self.ifc_file.create_entity("IfcRectangleProfileDef",
            ProfileType="AREA",
            XDim=length,
            YDim=thickness
        )
        
        # Позиция для экструзии
        position = self.ifc_file.create_entity("IfcAxis2Placement3D",
            Location=self.ifc_file.create_entity("IfcCartesianPoint", Coordinates=(start[0], start[1], start[2])),
            Axis=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            RefDirection=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        )
        
        # Экструдированная геометрия
        extrusion = self.ifc_file.create_entity("IfcExtrudedAreaSolid",
            SweptArea=rectangle,
            Position=self.ifc_file.create_entity("IfcAxis2Placement3D",
                Location=self.ifc_file.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
            ),
            ExtrudedDirection=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=height
        )
        
        # Создаем representation
        body_representation = self.ifc_file.create_entity("IfcShapeRepresentation",
            ContextOfItems=context,
            RepresentationIdentifier="Body",
            RepresentationType="SweptSolid",
            Items=[extrusion]
        )
        
        product_shape = self.ifc_file.create_entity("IfcProductDefinitionShape",
            Representations=[body_representation]
        )
        
        wall.Representation = product_shape
        wall.ObjectPlacement = self.ifc_file.create_entity("IfcLocalPlacement",
            RelativePlacement=position
        )
        
        ifcopenshell.api.run("spatial.assign_container", self.ifc_file,
            relating_structure=self.storey,
            products=[wall]
        )
        
        return wall
    
    def create_column(self, column_data: Dict[str, Any]):
        """
        Создание колонны (IfcColumn)
        """
        column = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcColumn",
            name=f"Column"
        )
        
        ifcopenshell.api.run("spatial.assign_container", self.ifc_file,
            relating_structure=self.storey,
            products=[column]
        )
        
        return column
    
    def generate(self) -> str:
        """
        Главная функция генерации IFC
        """
        print(f"Генерация IFC для задачи {self.task_id}...")
        
        # 1. Загружаем данные модели
        model_data = self.load_model_data()
        elements = model_data['elements']
        
        # 2. Создаем структуру IFC
        self.create_ifc_structure()
        
        # 3. Создаем плиты
        for slab in elements['slabs']:
            self.create_slab(slab)
        
        # 4. Создаем стены
        for wall in elements['walls']:
            self.create_wall(wall)
        
        # 5. Создаем колонны
        for column in elements['columns']:
            self.create_column(column)
        
        # 6. Сохраняем IFC файл
        output_path = f"exports/{self.task_id}.ifc"
        self.ifc_file.write(output_path)
        
        print(f"IFC файл сохранен: {output_path}")
        return output_path


def generate_ifc(task_id: str) -> str:
    """
    Функция для вызова из API
    """
    generator = IFCGenerator(task_id)
    return generator.generate()