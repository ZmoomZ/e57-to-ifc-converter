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
    
    def create_ifc_structure(self, storeys_count: int = 1):
        """
        Создание базовой структуры IFC файла с поддержкой нескольких этажей
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
        
        # Создаем этажи
        self.storeys = {}
        if storeys_count > 1:
            for i in range(storeys_count):
                storey = ifcopenshell.api.run("root.create_entity", self.ifc_file,
                    ifc_class="IfcBuildingStorey",
                    name=f"Floor {i}"
                )
                ifcopenshell.api.run("aggregate.assign_object", self.ifc_file,
                    relating_object=self.building, 
                    products=[storey]
                )
                self.storeys[i] = storey
        else:
            # Один этаж по умолчанию
            self.storey = ifcopenshell.api.run("root.create_entity", self.ifc_file,
                ifc_class="IfcBuildingStorey",
                name="Ground Floor"
            )
            ifcopenshell.api.run("aggregate.assign_object", self.ifc_file,
                relating_object=self.building, 
                products=[self.storey]
            )
            self.storeys[0] = self.storey
        
        print(f"IFC структура создана ({storeys_count} этажей)")
    
    def create_slab(self, slab_data: Dict[str, Any], bounds: Dict[str, List[float]]):
        """
        Создание плиты (IfcSlab) с геометрией
        """
        slab = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcSlab",
            name=f"Slab at Z={slab_data['z']:.2f}"
        )
        
        z_level = slab_data['z']
        thickness = slab_data['thickness']
        
        # Используем границы модели для размера плиты
        min_bounds = bounds['min']
        max_bounds = bounds['max']
        
        length = max_bounds[0] - min_bounds[0]
        width = max_bounds[1] - min_bounds[1]
        center_x = (max_bounds[0] + min_bounds[0]) / 2
        center_y = (max_bounds[1] + min_bounds[1]) / 2
        
        # Получаем контекст
        context = self.ifc_file.by_type("IfcGeometricRepresentationSubContext")[0]
        
        # Создаем прямоугольный профиль плиты
        rectangle = self.ifc_file.create_entity("IfcRectangleProfileDef",
            ProfileType="AREA",
            XDim=length,
            YDim=width
        )
        
        # Позиция экструзии
        extrusion_position = self.ifc_file.create_entity("IfcAxis2Placement3D",
            Location=self.ifc_file.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            RefDirection=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        )
        
        # Экструдированная геометрия
        extrusion = self.ifc_file.create_entity("IfcExtrudedAreaSolid",
            SweptArea=rectangle,
            Position=extrusion_position,
            ExtrudedDirection=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            Depth=thickness
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
        
        slab.Representation = product_shape
        
        # Размещение плиты
        placement_location = self.ifc_file.create_entity("IfcCartesianPoint", 
            Coordinates=(center_x, center_y, z_level)
        )
        
        axis_placement = self.ifc_file.create_entity("IfcAxis2Placement3D",
            Location=placement_location
        )
        
        slab.ObjectPlacement = self.ifc_file.create_entity("IfcLocalPlacement",
            RelativePlacement=axis_placement
        )
        
        ifcopenshell.api.run("spatial.assign_container", self.ifc_file,
            relating_structure=self.storeys[0],
            products=[slab]
        )
        
        return slab
    
    def create_wall(self, wall_data: Dict[str, Any]):
        """
        Создание стены (IfcWall) с правильной геометрией и ориентацией
        """
        import math
        
        wall = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcWall",
            name="Wall"
        )
        
        start = wall_data['start']
        end = wall_data['end']
        height = wall_data['height']
        thickness = wall_data['thickness']
        
        # Вычисляем длину и угол стены
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = math.sqrt(dx**2 + dy**2)
        
        if length < 0.1:  # Слишком короткая стена
            return None
        
        # Вычисляем угол поворота стены
        angle = math.atan2(dy, dx)
        
        # Направления для правильной ориентации
        cos_angle = math.cos(angle)
        sin_angle = math.sin(angle)
        
        # Получаем контекст
        context = self.ifc_file.by_type("IfcGeometricRepresentationSubContext")[0]
        
        # Создаем прямоугольный профиль стены
        rectangle = self.ifc_file.create_entity("IfcRectangleProfileDef",
            ProfileType="AREA",
            XDim=length,
            YDim=thickness
        )
        
        # Позиция экструзии (в начале стены)
        extrusion_position = self.ifc_file.create_entity("IfcAxis2Placement3D",
            Location=self.ifc_file.create_entity("IfcCartesianPoint", Coordinates=(0.0, -thickness/2, 0.0)),
            Axis=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            RefDirection=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        )
        
        # Экструдированная геометрия
        extrusion = self.ifc_file.create_entity("IfcExtrudedAreaSolid",
            SweptArea=rectangle,
            Position=extrusion_position,
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
        
        # Размещение стены в пространстве с правильным поворотом
        placement_location = self.ifc_file.create_entity("IfcCartesianPoint", 
            Coordinates=(start[0], start[1], start[2])
        )
        
        placement_axis = self.ifc_file.create_entity("IfcDirection", 
            DirectionRatios=(0.0, 0.0, 1.0)
        )
        
        placement_ref_direction = self.ifc_file.create_entity("IfcDirection", 
            DirectionRatios=(cos_angle, sin_angle, 0.0)
        )
        
        axis_placement = self.ifc_file.create_entity("IfcAxis2Placement3D",
            Location=placement_location,
            Axis=placement_axis,
            RefDirection=placement_ref_direction
        )
        
        wall.ObjectPlacement = self.ifc_file.create_entity("IfcLocalPlacement",
            RelativePlacement=axis_placement
        )
        
        # Определяем этаж для размещения
        storey_idx = wall_data.get('storey', 0)
        target_storey = self.storeys.get(storey_idx, self.storeys[0])
        
        ifcopenshell.api.run("spatial.assign_container", self.ifc_file,
            relating_structure=target_storey,
            products=[wall]
        )
        
        return wall
    
    def create_column(self, column_data: Dict[str, Any]):
        """
        Создание колонны (IfcColumn) с геометрией
        """
        column = ifcopenshell.api.run("root.create_entity", self.ifc_file,
            ifc_class="IfcColumn",
            name="Column"
        )
        
        position = column_data['position']
        height = column_data['height']
        width = column_data['width']
        depth = column_data['depth']
        
        # Получаем контекст
        context = self.ifc_file.by_type("IfcGeometricRepresentationSubContext")[0]
        
        # Создаем прямоугольный профиль колонны
        rectangle = self.ifc_file.create_entity("IfcRectangleProfileDef",
            ProfileType="AREA",
            XDim=width,
            YDim=depth
        )
        
        # Позиция экструзии
        extrusion_position = self.ifc_file.create_entity("IfcAxis2Placement3D",
            Location=self.ifc_file.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0)),
            Axis=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
            RefDirection=self.ifc_file.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0))
        )
        
        # Экструдированная геометрия
        extrusion = self.ifc_file.create_entity("IfcExtrudedAreaSolid",
            SweptArea=rectangle,
            Position=extrusion_position,
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
        
        column.Representation = product_shape
        
        # Размещение колонны
        placement_location = self.ifc_file.create_entity("IfcCartesianPoint", 
            Coordinates=(position[0], position[1], position[2])
        )
        
        axis_placement = self.ifc_file.create_entity("IfcAxis2Placement3D",
            Location=placement_location
        )
        
        column.ObjectPlacement = self.ifc_file.create_entity("IfcLocalPlacement",
            RelativePlacement=axis_placement
        )
        
        # Определяем этаж для размещения
        storey_idx = column_data.get('storey', 0)
        target_storey = self.storeys.get(storey_idx, self.storeys[0])
        
        ifcopenshell.api.run("spatial.assign_container", self.ifc_file,
            relating_structure=target_storey,
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
        storeys_count = len(model_data.get('storeys', []))
        if storeys_count == 0:
            storeys_count = 1
        self.create_ifc_structure(storeys_count)
        
        # 3. Создаем плиты
        for slab in elements['slabs']:
            self.create_slab(slab, model_data['bounds'])
        
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