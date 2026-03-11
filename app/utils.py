def seed_plans_from_dict():
    """One-time migration: copy PLANS dict → Plan table."""
    for i, (key, data) in enumerate(PLANS.items()):
        if Plan.query.filter_by(plan_key=key).first():
            continue
        p = Plan(
            plan_key    = key,
            name        = data['name'],
            price_usd   = data['price_usd'],
            interval    = data.get('interval', 'month'),
            shipments   = data.get('shipments'),
            is_active   = True,
            is_featured = (key == 'professional'),
            sort_order  = i,
        )
        p.features = data.get('features', [])
        db.session.add(p)
    db.session.commit()
    print("Plans seeded.")

