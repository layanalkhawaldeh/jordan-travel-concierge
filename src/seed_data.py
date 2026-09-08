import os
import json
from src.database import SessionLocal, HotelModel, ActivityModel, TransportationModel, PromptModel, init_db

def seed_database():
    print("Initializing database schema...")
    init_db()
    
    db = SessionLocal()
    try:
        # 1. Seed Hotels
        if db.query(HotelModel).count() == 0:
            print("Seeding hotels...")
            hotels = [
                HotelModel(name="W Amman", city="Amman", stars=5, price_per_night=180.0, capacity=2, amenities=["Pool", "Gym", "Spa", "Free WiFi"], availability_status=True),
                HotelModel(name="Amman Rotana", city="Amman", stars=5, price_per_night=150.0, capacity=2, amenities=["Pool", "Gym", "Free WiFi", "Valet Parking"], availability_status=True),
                HotelModel(name="AlQasr Metropole Hotel", city="Amman", stars=4, price_per_night=95.0, capacity=2, amenities=["Free WiFi", "Restaurant", "Bar"], availability_status=True),
                HotelModel(name="Larsa Hotel", city="Amman", stars=3, price_per_night=50.0, capacity=3, amenities=["Free WiFi", "Gym", "Breakfast"], availability_status=True),
                
                HotelModel(name="Movenpick Resort Petra", city="Petra", stars=5, price_per_night=220.0, capacity=2, amenities=["Pool", "Spa", "Free WiFi", "Near Visitor Center"], availability_status=True),
                HotelModel(name="Petra Bubble Luxotel", city="Petra", stars=5, price_per_night=260.0, capacity=2, amenities=["Jacuzzi", "Stargazing Deck", "Dinner Included"], availability_status=True),
                HotelModel(name="Edom Hotel", city="Petra", stars=3, price_per_night=60.0, capacity=2, amenities=["Free WiFi", "Rooftop Terrace"], availability_status=True),
                HotelModel(name="Seven Wonders Bedouin Camp", city="Petra", stars=2, price_per_night=40.0, capacity=4, amenities=["Shared Bathroom", "Traditional Dinner", "Campfire"], availability_status=True),
                
                HotelModel(name="Kempinski Hotel Ishtar Dead Sea", city="Dead Sea", stars=5, price_per_night=250.0, capacity=2, amenities=["Infinity Pool", "Private Beach", "Luxury Spa", "Free WiFi"], availability_status=True),
                HotelModel(name="Crowne Plaza Jordan Dead Sea", city="Dead Sea", stars=5, price_per_night=140.0, capacity=2, amenities=["Huge Pool", "Private Beach", "Gym"], availability_status=True),
                HotelModel(name="Dead Sea Spa Hotel", city="Dead Sea", stars=4, price_per_night=85.0, capacity=2, amenities=["Pool", "Mud Treatment", "Free WiFi"], availability_status=True),
                
                HotelModel(name="Wadi Rum Bubble Luxotel", city="Wadi Rum", stars=5, price_per_night=280.0, capacity=2, amenities=["Stargazing Dome", "Jacuzzi", "Dinner Included"], availability_status=True),
                HotelModel(name="Sun City Camp", city="Wadi Rum", stars=4, price_per_night=130.0, capacity=2, amenities=["Martian Dome", "Dinner Included", "Jeep Tour Booking"], availability_status=True),
                HotelModel(name="Wadi Rum Quiet Camp", city="Wadi Rum", stars=2, price_per_night=45.0, capacity=3, amenities=["Traditional Tents", "Dinner Included", "Camel Tours"], availability_status=True),
                
                HotelModel(name="InterContinental Aqaba", city="Aqaba", stars=5, price_per_night=190.0, capacity=2, amenities=["Private Beach", "Pool", "Watersports", "Free WiFi"], availability_status=True),
                HotelModel(name="DoubleTree by Hilton Aqaba", city="Aqaba", stars=5, price_per_night=110.0, capacity=2, amenities=["Rooftop Pool", "Gym", "Free WiFi"], availability_status=True),
                HotelModel(name="My Hotel Aqaba", city="Aqaba", stars=3, price_per_night=55.0, capacity=2, amenities=["Free WiFi", "Rooftop Restaurant"], availability_status=True)
            ]
            db.bulk_save_objects(hotels)
            db.commit()
            print(f"Seeded {len(hotels)} hotels.")

        # 2. Seed Activities
        if db.query(ActivityModel).count() == 0:
            print("Seeding activities...")
            activities = [
                ActivityModel(name="Petra Guided Tour", city="Petra", price=50.0, interest_type="history", description="Explore the Treasury and Monastery with a local guide."),
                ActivityModel(name="Petra by Night", city="Petra", price=25.0, interest_type="history", description="Walk through the Siq lit by 1,500 candles at night."),
                ActivityModel(name="4x4 Jeep Safari Tour", city="Wadi Rum", price=40.0, interest_type="adventure", description="2-hour jeep ride through sand dunes and rock bridges."),
                ActivityModel(name="Camel Riding at Sunrise", city="Wadi Rum", price=30.0, interest_type="adventure", description="Traditional camel trek across red sands."),
                ActivityModel(name="Dead Sea Mud Bath & Floating", city="Dead Sea", price=15.0, interest_type="relaxation", description="Float in hyper-saline waters and enjoy mineral mud."),
                ActivityModel(name="Amman Citadel & Roman Theater Walk", city="Amman", price=20.0, interest_type="history", description="Visit historical monuments in downtown Amman."),
                ActivityModel(name="Snorkeling & Boat Trip", city="Aqaba", price=45.0, interest_type="adventure", description="Cruise the Red Sea with lunch and snorkeling gear."),
                ActivityModel(name="Scuba Diving in Red Sea", city="Aqaba", price=75.0, interest_type="adventure", description="Discover shipwrecks and coral gardens under water.")
            ]
            db.bulk_save_objects(activities)
            db.commit()
            print(f"Seeded {len(activities)} activities.")

        # 3. Seed Transportation
        if db.query(TransportationModel).count() == 0:
            print("Seeding transportation options...")
            transportations = [
                TransportationModel(type="Private Driver", price_per_day=90.0, description="English-speaking driver with air-conditioned sedan."),
                TransportationModel(type="Rental Car", price_per_day=40.0, description="Economy or SUV car hire with unlimited mileage."),
                TransportationModel(type="Public Bus", price_per_day=15.0, description="JETT bus service connecting Amman, Petra, Dead Sea, and Aqaba.")
            ]
            db.bulk_save_objects(transportations)
            db.commit()
            print(f"Seeded {len(transportations)} transportation options.")

        # 4. Seed Prompts from prompts.json
        print("Seeding/updating prompts table from prompts.json...")
        current_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(current_dir, "prompts", "prompts.json")
        
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                prompts_dict = json.load(f)
                
            for p_id, p_data in prompts_dict.items():
                existing = db.query(PromptModel).filter(PromptModel.id == p_id).first()
                if existing:
                    existing.prompt_data = p_data
                else:
                    db.add(PromptModel(
                        id=p_id, 
                        prompt_data=p_data, 
                        description=f"{p_id.replace('_', ' ').title()} prompt template."
                    ))
            db.commit()
            print(f"Upserted {len(prompts_dict)} prompts from JSON file into PostgreSQL database.")
        else:
            print(f"Warning: Prompts file not found at {json_path}")
            
        print("Database seeding completed successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding database: {e}")
        raise e
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
